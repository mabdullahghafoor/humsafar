"""
Panic Mode (Task 3.6, FR-D2).

The Dependent presses one button: POST /dependents/{id}/panic. The server
  1. opens a `panic` escalation event (critical),
  2. tells EVERY linked Guardian at once, Primary and Secondaries, WHATEVER their permissions (the one deliberate
     exception to permission gating; notification_service audience `all_linked`),
  3. leaves it to the escalation chain (Task 3.5): if nobody opens the alert in time it moves to the
     external-contact level (SMS in Task 3.8).
Only one panic can be open per Dependent: pressing again changes nothing (`already_active`), so a nervous
double tap or a retry on a bad network does not spam the Guardians.
It closes when the Dependent cancels ("I am safe") or the Primary Guardian marks it handled. Everybody who was told
gets a standard all-clear. Pressing the button never needs a verified account, a link or a permission check beyond
being this Dependent: when seconds count, nothing may get in the way. With no Guardian linked yet the event is
still recorded (nobody can be told).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AuditLog, EscalationEvent, Notification, User
from app.schemas.panic import PanicOut, PanicStatusOut
from app.services import linkage_service, notification_service, permission_service

TRIGGER = "panic"
OPEN, RESOLVED = "open", "resolved"


def _own_dependent(user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")


def _open_panic(db: Session, dependent_id: uuid.UUID, lock: bool = False) -> EscalationEvent | None:
    q = select(EscalationEvent).where(
        EscalationEvent.dependent_id == dependent_id, EscalationEvent.trigger_type == TRIGGER, EscalationEvent.status == OPEN
    )
    return db.scalar(q.with_for_update() if lock else q)


def _told(db: Session, ev: EscalationEvent) -> int:
    return db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.payload["event_id"].astext == str(ev.event_id), Notification.payload["dedupe_key"].astext.like("%:open")
        )
    ) or 0


def _out(ev: EscalationEvent, notified: int | None = None, already: bool = False) -> PanicOut:
    return PanicOut(
        event_id=ev.event_id, status=ev.status, tier=ev.tier, triggered_at=ev.created_at, acknowledged_at=ev.acknowledged_at,
        resolved_at=ev.resolved_at, notified=notified, already_active=already,
    )


def trigger(db: Session, user: User, dependent_id: uuid.UUID) -> tuple[PanicOut, bool]:
    """Returns (panic, created). `created` is False when a panic was already open."""
    _own_dependent(user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)  # two taps at once -> one panic
    ev = _open_panic(db, dependent_id)
    if ev is not None:
        out = _out(ev, _told(db, ev), already=True)
        db.rollback()
        return out, False
    ev = EscalationEvent(event_id=uuid.uuid4(), dependent_id=dependent_id, trigger_type=TRIGGER, tier="primary")
    db.add(ev)
    db.add(AuditLog(actor_id=user.user_id, action="panic_triggered", target_type="escalation_event", target_id=ev.event_id))
    db.commit()  # the panic is saved before anything else can go wrong
    notification_service.dispatch_events_safely(db, dependent_id)
    db.refresh(ev)
    return _out(ev, _told(db, ev)), True


def status(db: Session, user: User, dependent_id: uuid.UUID) -> PanicStatusOut:
    """Any linked Guardian (no module permission needed, as for the alert itself) or the Dependent."""
    if user.role == "dependent":
        _own_dependent(user, dependent_id)
    elif user.role != "guardian" or permission_service._my_link(db, user.user_id, dependent_id) is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT" if user.role == "guardian" else "FORBIDDEN", "You do not have permission to do this.")
    ev = _open_panic(db, dependent_id)
    return PanicStatusOut(active=ev is not None, panic=_out(ev, _told(db, ev)) if ev else None)


def resolve(db: Session, user: User, dependent_id: uuid.UUID) -> PanicOut:
    """The Dependent cancels ("I am safe") or the Primary Guardian marks it handled."""
    if user.role == "dependent":
        _own_dependent(user, dependent_id)
    else:
        linkage_service._guardian_profile(db, user)
        if not linkage_service._is_primary_of(db, user.user_id, dependent_id):
            raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can close a panic alert.")
    linkage_service._lock_dependent(db, dependent_id)
    ev = _open_panic(db, dependent_id, lock=True)
    if ev is None:
        db.rollback()
        raise AppError(409, "NO_ACTIVE_PANIC", "There is no open panic alert.")
    ev.status, ev.resolved_at = RESOLVED, datetime.now(timezone.utc)
    db.add(AuditLog(actor_id=user.user_id, action="panic_resolved", target_type="escalation_event", target_id=ev.event_id))
    db.commit()
    notification_service.dispatch_events_safely(db, dependent_id)
    db.refresh(ev)
    return _out(ev, _told(db, ev))
