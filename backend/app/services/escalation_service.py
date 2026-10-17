"""
Multi-level escalation chain (Task 3.5, FR-D5).

An alert that needs a person (a missed dose, an unanswered wellness check, a panic) is an `escalation_events` row.
It starts at the PRIMARY level: the Primary Guardian is told (notification_service). Then a timer runs:

    primary     --- not opened within ESCALATION_PRIMARY_TIMEOUT_S (5 min) --->  secondary
    secondary   --- not opened within ESCALATION_SECONDARY_TIMEOUT_S (5 min) --> external_contact

"Opened" = a Guardian acknowledged the critical notification of the event (FR-M2). That stops the chain at the
level it reached. (The event stays open until the problem itself is solved.)
- A level with nobody to tell (no Secondary linked, or none with `emergency_alerts`) is skipped.
- Panic tells every Guardian at once (audience all_linked), so it goes from primary straight to external_contact.
- The external_contact level is where the SMS fallback (Task 3.8) acts. This module only moves the event there.
- Only these event types escalate by timer: ESCALATING. A geofence breach or low battery is told once.
- A Guardian can also push an alert up by hand (missed dose: POST .../escalate, Task 3.3); that restarts the timer.

The job `sweep` runs every minute; the dispatcher (notification_service.dispatch_events) runs right after it and
tells the people of the new level. Safe with several processes: each event is locked with SKIP LOCKED.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import EscalationEvent, Notification, User
from app.schemas.escalation import EscalationListOut, EscalationOut
from app.services import notification_service, permission_service
from app.services.notification_service import ALL_LINKED, BY_TIER, EVENT_RULES

MODULE = "emergency_alerts"
ESCALATING = ("missed_dose", "wellness_check", "panic")
OPEN = "open"
_NEXT = {"primary": "secondary", "secondary": "external_contact"}


def timeout_s(tier: str) -> int | None:
    s = get_settings()
    return {"primary": s.ESCALATION_PRIMARY_TIMEOUT_S, "secondary": s.ESCALATION_SECONDARY_TIMEOUT_S}.get(tier)


def next_tier(db: Session, ev: EscalationEvent) -> str | None:
    """The next level that has someone to tell. 'external_contact' always counts (Task 3.8 decides what to send)."""
    rule = EVENT_RULES[ev.trigger_type]
    tier = ev.tier
    while tier in _NEXT:
        tier = _NEXT[tier]
        if tier == "external_contact":
            return tier
        if rule.audience == ALL_LINKED:  # everyone was told at once; no separate Secondary level
            continue
        if notification_service.recipients(db, ev.dependent_id, rule.audience, tier):
            return tier
    return None


def _first_ack(db: Session, event_id: uuid.UUID) -> Notification | None:
    """The earliest acknowledged 'open' alert of this event (the all-clear notifications do not count)."""
    return db.scalar(
        select(Notification)
        .where(
            Notification.payload["event_id"].astext == str(event_id),
            Notification.payload["dedupe_key"].astext.like("%:open"),
            Notification.acknowledged_at.is_not(None),
        )
        .order_by(Notification.acknowledged_at)
        .limit(1)
    )


def sweep(db: Session, now: datetime | None = None) -> int:
    """Move every open, unopened alert whose timer ran out to the next level. Returns how many moved."""
    now = now or datetime.now(timezone.utc)
    s = get_settings()
    shortest = min(s.ESCALATION_PRIMARY_TIMEOUT_S, s.ESCALATION_SECONDARY_TIMEOUT_S)
    ids = db.scalars(
        select(EscalationEvent.event_id).where(
            EscalationEvent.status == OPEN,
            EscalationEvent.trigger_type.in_(ESCALATING),
            EscalationEvent.tier.in_(tuple(_NEXT)),
            EscalationEvent.acknowledged_at.is_(None),
            EscalationEvent.tier_changed_at <= now - timedelta(seconds=shortest),
        )
    ).all()
    moved = 0
    for event_id in ids:
        ev = db.scalar(select(EscalationEvent).where(EscalationEvent.event_id == event_id).with_for_update(skip_locked=True))
        if ev is None:  # another process has it
            continue
        t = timeout_s(ev.tier)
        if ev.status != OPEN or ev.acknowledged_at is not None or t is None or ev.tier_changed_at > now - timedelta(seconds=t):
            db.rollback()
            continue
        ack = _first_ack(db, ev.event_id)
        if ack is not None:  # somebody opened it: the chain stops here
            ev.acknowledged_at, ev.acknowledged_by = ack.acknowledged_at, ack.user_id
            db.commit()
            continue
        nxt = next_tier(db, ev)
        if nxt is None:
            db.rollback()
            continue
        ev.tier, ev.tier_changed_at = nxt, now
        db.commit()
        moved += 1
    return moved


# ------------------------------------------------------------------ API

def _out(ev: EscalationEvent) -> EscalationOut:
    t = timeout_s(ev.tier)
    nxt_at = None
    if ev.status == OPEN and ev.acknowledged_at is None and ev.trigger_type in ESCALATING and t is not None:
        nxt_at = ev.tier_changed_at + timedelta(seconds=t)
    return EscalationOut(
        event_id=ev.event_id, trigger_type=ev.trigger_type, reference_id=ev.reference_id, tier=ev.tier, status=ev.status,
        created_at=ev.created_at, tier_changed_at=ev.tier_changed_at, acknowledged_at=ev.acknowledged_at,
        acknowledged_by=ev.acknowledged_by, resolved_at=ev.resolved_at, next_escalation_at=nxt_at,
    )


def list_events(db: Session, user: User, dependent_id: uuid.UUID, status: str | None = None, limit: int = 50) -> EscalationListOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    q = select(EscalationEvent).where(EscalationEvent.dependent_id == dependent_id, EscalationEvent.trigger_type.in_(EVENT_RULES))
    if status:
        q = q.where(EscalationEvent.status == status)
    rows = db.scalars(q.order_by(EscalationEvent.created_at.desc()).limit(limit)).all()
    s = get_settings()
    return EscalationListOut(
        primary_timeout_s=s.ESCALATION_PRIMARY_TIMEOUT_S, secondary_timeout_s=s.ESCALATION_SECONDARY_TIMEOUT_S,
        items=[_out(e) for e in rows],
    )


def acknowledge_event(db: Session, user: User, event_id: uuid.UUID) -> EscalationOut:
    """
    "I have seen this alert": acknowledges the caller's own alerts of this event (same as tapping each one) and stops
    the chain. Idempotent: the first time is kept. Someone who was never told looks like 'not found'.
    """
    mine = db.scalars(
        select(Notification)
        .where(
            Notification.user_id == user.user_id,
            Notification.payload["event_id"].astext == str(event_id),
            Notification.payload["dedupe_key"].astext.like("%:open"),
        )
        .with_for_update()
    ).all()
    if not mine:
        db.rollback()
        raise AppError(404, "ESCALATION_NOT_FOUND", "Alert not found.")
    now = datetime.now(timezone.utc)
    for n in mine:
        if n.acknowledged_at is None:
            n.acknowledged_at = now
    ev = db.scalar(select(EscalationEvent).where(EscalationEvent.event_id == event_id).with_for_update())
    if ev.acknowledged_at is None:
        ev.acknowledged_at, ev.acknowledged_by = now, user.user_id
    db.commit()
    db.refresh(ev)
    return _out(ev)
