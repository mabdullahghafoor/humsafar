"""
Notification service (Task 3.1, FR-M1 / FR-M2; SDS 7.1 "Notification Module").

Two jobs:
  1. NotificationDispatcher: turn an event (a geofence breach, low battery, panic ...) into notifications for
     the right people, in one of two priority tiers (standard / critical), and push them to their phones.
  2. AcknowledgmentTracker: record when a person opens/acknowledges a notification, so an unacknowledged
     critical alert is visible as "no response" (feeds the escalation engine, Task 3.5).

Who is told (clarification items 16, 21, 25):
  * linked_permitted  Primary, plus each Secondary who is verified AND has 'emergency_alerts'.
  * by_tier           the escalation chain: tier 'primary' -> Primary only; tier 'secondary' -> permitted
                      Secondaries; tier 'external_contact' -> nobody here (SMS fallback is Task 3.8).
  * all_linked        Panic Mode: every linked Guardian, permissions ignored (FR-D2, Task 3.6).

Every notification carries a dedupe key, enforced by a unique index, so a retried or simultaneous dispatch
can never tell the same person about the same event twice.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    EscalationEvent,
    GuardianDependentLink,
    GuardianProfile,
    Notification,
    PermissionGrant,
    PushToken,
    User,
)
from app.schemas.notification import NotificationList, NotificationOut
from app.services import push_service
from app.services.push_service import PushMessage

log = logging.getLogger("humsafar.notifications")

STANDARD, CRITICAL = "standard", "critical"
ACTIVE, OPEN, RESOLVED = "active", "open", "resolved"
LINKED_PERMITTED, BY_TIER, ALL_LINKED = "linked_permitted", "by_tier", "all_linked"


@dataclass(frozen=True)
class Rule:
    title: str
    body: str  # {name} = the Dependent's name
    audience: str
    resolved_title: str | None = None  # a standard "all clear" is sent when the event closes
    resolved_body: str | None = None


# FR-M1: these are all critical. Keyed by escalation_events.trigger_type.
EVENT_RULES: dict[str, Rule] = {
    "geofence_breach": Rule("Left the safe zone", "{name} has left the safe zone.", LINKED_PERMITTED,
                            "Back in the safe zone", "{name} is back inside a safe zone."),
    "low_battery": Rule("Low battery", "{name}'s phone battery is low.", LINKED_PERMITTED,
                        "Battery recovered", "{name}'s phone battery is back to a safe level."),
    "device_offline": Rule("Connection lost", "{name}'s phone has gone offline.", LINKED_PERMITTED,
                           "Back online", "{name}'s phone is back online."),
    "fall": Rule("Possible fall", "{name} may have fallen.", LINKED_PERMITTED),
    "missed_dose": Rule("Missed medication", "{name} has not confirmed a medication dose.", BY_TIER),
    "wellness_check": Rule("Wellness check not answered", "{name} has not answered the wellness check.", BY_TIER),
    "panic": Rule("PANIC ALERT", "{name} pressed the panic button and needs help now.", ALL_LINKED),
}


# ------------------------------------------------------------ who gets told

def _verified(profile: GuardianProfile | None) -> bool:
    return profile is not None and (profile.phone_verified or profile.cnic_verified)


def recipients(db: Session, dependent_id: uuid.UUID, audience: str, tier: str = "primary") -> list[uuid.UUID]:
    """User ids of the Guardians to notify, Primary first. Only ACTIVE links count."""
    links = db.scalars(
        select(GuardianDependentLink).where(
            GuardianDependentLink.dependent_id == dependent_id, GuardianDependentLink.status == ACTIVE
        )
    ).all()
    primary = [l.guardian_id for l in links if l.role == "primary"]
    secondaries = [l for l in links if l.role == "secondary"]

    def permitted(link: GuardianDependentLink) -> bool:
        if not _verified(db.get(GuardianProfile, link.guardian_id)):
            return False
        grant = db.scalar(
            select(PermissionGrant).where(PermissionGrant.link_id == link.link_id, PermissionGrant.module == "emergency_alerts")
        )
        return bool(grant and grant.granted)

    if audience == ALL_LINKED:  # Panic Mode: the one deliberate exception to the permission model
        return primary + [l.guardian_id for l in secondaries]
    if audience == BY_TIER:
        if tier == "primary":
            return primary
        if tier == "secondary":
            return [l.guardian_id for l in secondaries if permitted(l)]
        return []  # 'external_contact' is handled by the SMS fallback (Task 3.8)
    return primary + [l.guardian_id for l in secondaries if permitted(l)]  # LINKED_PERMITTED


# ------------------------------------------------------------ sending

def _push_tokens(db: Session, user_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(PushToken.token).where(PushToken.user_id == user_id)))


def notify(
    db: Session,
    user_id: uuid.UUID,
    type: str,
    priority: str,
    title: str,
    body: str,
    *,
    dependent_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    extra: dict | None = None,
) -> Notification | None:
    """
    Save one notification and push it. Returns None if the same dedupe_key was already used for this person
    (nothing is sent twice). Commits. The push happens after the commit and can fail without losing the row.
    """
    if priority not in (STANDARD, CRITICAL):
        raise ValueError("priority must be 'standard' or 'critical'")
    payload = {"title": title, "body": body, **(extra or {})}
    if dependent_id:
        payload["dependent_id"] = str(dependent_id)
    if event_id:
        payload["event_id"] = str(event_id)
    if dedupe_key:
        payload["dedupe_key"] = dedupe_key
    stmt = (
        pg_insert(Notification)
        .values(notification_id=uuid.uuid4(), user_id=user_id, type=type, priority=priority, payload=payload)
        .on_conflict_do_nothing()
        .returning(Notification.notification_id)
    )
    new_id = db.execute(stmt).scalar()
    db.commit()
    if new_id is None:
        return None
    note = db.get(Notification, new_id)
    push_service.deliver(
        PushMessage(
            tokens=_push_tokens(db, user_id),
            title=title,
            body=body,
            priority=priority,
            data={"notification_id": str(new_id), "type": type, "priority": priority, **({"event_id": str(event_id)} if event_id else {})},
        )
    )
    return note


def _display_name(db: Session, dependent_id: uuid.UUID) -> str:
    user = db.get(User, dependent_id)
    return (user.full_name or "").strip() or "Your dependent" if user else "Your dependent"


def _notify_event(db: Session, ev: EscalationEvent, rule: Rule) -> int:
    name = _display_name(db, ev.dependent_id)
    sent = 0
    for uid in recipients(db, ev.dependent_id, rule.audience, ev.tier):
        n = notify(
            db, uid, ev.trigger_type, CRITICAL, rule.title, rule.body.format(name=name),
            dependent_id=ev.dependent_id, event_id=ev.event_id, dedupe_key=f"{ev.event_id}:{ev.tier}:open",
            extra={"tier": ev.tier},
        )
        sent += n is not None
    return sent


def _notify_resolved(db: Session, ev: EscalationEvent, rule: Rule) -> int:
    """A standard-tier "all clear", only to people who were told about the problem."""
    name = _display_name(db, ev.dependent_id)
    told = db.scalars(
        select(Notification.user_id).where(
            Notification.payload["event_id"].astext == str(ev.event_id), Notification.payload["dedupe_key"].astext.like("%:open")
        )
    ).all()
    sent = 0
    for uid in set(told):
        n = notify(
            db, uid, ev.trigger_type, STANDARD, rule.resolved_title, rule.resolved_body.format(name=name),
            dependent_id=ev.dependent_id, event_id=ev.event_id, dedupe_key=f"{ev.event_id}:resolved",
            extra={"resolved": True},
        )
        sent += n is not None
    return sent


def dispatch_events(db: Session, dependent_id: uuid.UUID | None = None) -> int:
    """
    Tell people about escalation events they have not been told about yet, and send the standard "all clear"
    for events that have closed. Safe to run often and from several processes at once. Returns how many
    notifications were created. `dependent_id` limits it to one Dependent (used right after a location fix).
    """
    created = 0
    q = select(EscalationEvent).where(EscalationEvent.status == OPEN, EscalationEvent.trigger_type.in_(EVENT_RULES))
    if dependent_id:
        q = q.where(EscalationEvent.dependent_id == dependent_id)
    for ev in db.scalars(q).all():
        created += _notify_event(db, ev, EVENT_RULES[ev.trigger_type])

    since = datetime.now(timezone.utc) - timedelta(seconds=get_settings().NOTIFY_RESOLVED_WINDOW_S)
    resolvable = [k for k, r in EVENT_RULES.items() if r.resolved_title]
    q = select(EscalationEvent).where(
        EscalationEvent.status == RESOLVED, EscalationEvent.resolved_at >= since, EscalationEvent.trigger_type.in_(resolvable)
    )
    if dependent_id:
        q = q.where(EscalationEvent.dependent_id == dependent_id)
    for ev in db.scalars(q).all():
        created += _notify_resolved(db, ev, EVENT_RULES[ev.trigger_type])
    return created


def dispatch_events_safely(db: Session, dependent_id: uuid.UUID) -> None:
    """Called right after a location fix. A notification problem must never fail the phone's upload."""
    try:
        dispatch_events(db, dependent_id)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("dispatching notifications failed for %s", dependent_id)


def notify_dependent_guardians(
    db: Session,
    dependent_id: uuid.UUID,
    type: str,
    title: str,
    body: str,
    *,
    audience: str = LINKED_PERMITTED,
    tier: str = "primary",
    priority: str = CRITICAL,
    event_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> list[Notification]:
    """For the Phase 3 features (medication, wellness check, panic): notify a Dependent's Guardians directly."""
    out = []
    for uid in recipients(db, dependent_id, audience, tier):
        key = f"{dedupe_key}:{uid}" if dedupe_key else None
        n = notify(db, uid, type, priority, title, body, dependent_id=dependent_id, event_id=event_id, dedupe_key=key)
        if n:
            out.append(n)
    return out


# ------------------------------------------------------------ reading and acknowledging (FR-M2)

def _out(n: Notification) -> NotificationOut:
    p = n.payload or {}
    return NotificationOut(
        notification_id=n.notification_id,
        type=n.type,
        priority=n.priority,
        title=p.get("title", ""),
        body=p.get("body", ""),
        dependent_id=p.get("dependent_id"),
        event_id=p.get("event_id"),
        data={k: v for k, v in p.items() if k not in ("title", "body", "dedupe_key")},
        sent_at=n.sent_at,
        acknowledged_at=n.acknowledged_at,
        is_acknowledged=n.acknowledged_at is not None,
    )


def list_for_user(
    db: Session, user: User, *, priority: str | None, unacknowledged: bool, limit: int, before: datetime | None
) -> NotificationList:
    q = select(Notification).where(Notification.user_id == user.user_id)
    if priority:
        q = q.where(Notification.priority == priority)
    if unacknowledged:
        q = q.where(Notification.acknowledged_at.is_(None))
    if before:
        q = q.where(Notification.sent_at < before)
    rows = db.scalars(q.order_by(Notification.sent_at.desc(), Notification.notification_id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    pending = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user.user_id, Notification.priority == CRITICAL, Notification.acknowledged_at.is_(None)
        )
    )
    return NotificationList(
        items=[_out(n) for n in rows],
        unacknowledged_critical=pending or 0,
        next_before=rows[-1].sent_at if more and rows else None,
    )


def acknowledge(db: Session, user: User, notification_id: uuid.UUID) -> NotificationOut:
    """FR-M2. Idempotent: the FIRST acknowledgment time is kept. Someone else's notification looks like 'not found'."""
    n = db.scalar(
        select(Notification).where(Notification.notification_id == notification_id, Notification.user_id == user.user_id).with_for_update()
    )
    if n is None:
        raise AppError(404, "NOTIFICATION_NOT_FOUND", "Notification not found.")
    if n.acknowledged_at is None:
        n.acknowledged_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(n)
    return _out(n)


def unacknowledged_critical(db: Session, older_than_s: int = 0, event_id: uuid.UUID | None = None) -> list[Notification]:
    """
    The "no response" state (FR-M2 -> FR-D5): critical notifications still unacknowledged after `older_than_s`
    seconds. The escalation engine (Task 3.5) uses this.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_s)
    q = select(Notification).where(
        Notification.priority == CRITICAL, Notification.acknowledged_at.is_(None), Notification.sent_at <= cutoff
    )
    if event_id:
        q = q.where(Notification.payload["event_id"].astext == str(event_id))
    return list(db.scalars(q.order_by(Notification.sent_at)).all())


# ------------------------------------------------------------ push tokens

def register_push_token(db: Session, user: User, token: str, platform: str) -> None:
    """One row per token. If the phone is now used by someone else, the token moves to the new user."""
    stmt = (
        pg_insert(PushToken)
        .values(token_id=uuid.uuid4(), user_id=user.user_id, token=token, platform=platform)
        .on_conflict_do_update(index_elements=[PushToken.token], set_={"user_id": user.user_id, "platform": platform, "last_seen_at": func.now()})
    )
    db.execute(stmt)
    db.commit()


def unregister_push_token(db: Session, user: User, token: str) -> None:
    row = db.scalar(select(PushToken).where(PushToken.token == token, PushToken.user_id == user.user_id))
    if row is not None:
        db.delete(row)
        db.commit()
