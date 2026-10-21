"""
Remote Alarm Override (Task 3.7, FR-D3).

The PRIMARY Guardian (and nobody else, whatever a Secondary has been granted: the permission dashboard cannot
delegate it) can make the Dependent's phone sound a loud alarm, for example to find a confused person nearby.
  POST /dependents/{id}/alarm         start it (10 to 300 s, default 60)
  GET  /dependents/{id}/alarm         is one sounding? (the Primary, or the Dependent's own phone as a fallback to the push)
  POST /dependents/{id}/alarm/stop    stop it (the Primary, or the Dependent)

How it works with no extra table: an alarm is a critical `remote_alarm` notification sent to the Dependent
(push + inbox) that carries `alarm_id`, `duration_s` and `expires_at`. Stopping sends a `remote_alarm_stop`
notification with the same `alarm_id`. The alarm is "active" while the newest of those two is a `remote_alarm`
that has not expired. The phone app does the sound: it must override the silent / volume state "subject to Android
OS permission APIs" (SRS FR-D3); the server only delivers the order and records it (audit log).
One alarm at a time: starting again while one sounds changes nothing (`already_active`).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, Notification, User
from app.schemas.alarm import AlarmOut, AlarmStatusOut
from app.services import linkage_service, notification_service, permission_service
from app.services.notification_service import CRITICAL

START, STOP = "remote_alarm", "remote_alarm_stop"


def _require_primary(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    link = permission_service._my_link(db, user.user_id, dependent_id)
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    if link.role != "primary":
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can sound the alarm.")
    profile = linkage_service._guardian_profile(db, user)
    if not (profile.phone_verified or profile.cnic_verified):
        raise AppError(403, "GUARDIAN_NOT_VERIFIED", "Verify your phone number or CNIC before using this feature.")


def _latest(db: Session, dependent_id: uuid.UUID) -> Notification | None:
    return db.scalar(
        select(Notification)
        .where(Notification.user_id == dependent_id, Notification.type.in_((START, STOP)))
        .order_by(Notification.sent_at.desc(), Notification.notification_id.desc())
        .limit(1)
    )


def _start_row(db: Session, dependent_id: uuid.UUID, alarm_id: str) -> Notification | None:
    return db.scalar(
        select(Notification).where(
            Notification.user_id == dependent_id, Notification.type == START, Notification.payload["alarm_id"].astext == alarm_id
        )
    )


def _out(db: Session, start: Notification, now: datetime, already: bool = False) -> AlarmOut:
    p = start.payload
    stop = db.scalar(
        select(Notification).where(
            Notification.user_id == start.user_id, Notification.type == STOP, Notification.payload["alarm_id"].astext == p["alarm_id"]
        )
    )
    expires = datetime.fromisoformat(p["expires_at"])
    status = "stopped" if stop else ("expired" if expires <= now else "active")
    return AlarmOut(
        alarm_id=uuid.UUID(p["alarm_id"]), status=status, triggered_by=uuid.UUID(p["triggered_by"]), triggered_at=start.sent_at,
        duration_s=p["duration_s"], expires_at=expires, stopped_at=stop.sent_at if stop else None,
        device_acknowledged_at=start.acknowledged_at, already_active=already,
    )


def _active(db: Session, dependent_id: uuid.UUID, now: datetime) -> Notification | None:
    last = _latest(db, dependent_id)
    if last is None or last.type != START:
        return None
    return last if datetime.fromisoformat(last.payload["expires_at"]) > now else None


def trigger(db: Session, user: User, dependent_id: uuid.UUID, duration_s: int | None) -> tuple[AlarmOut, bool]:
    _require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)  # two requests at once -> one alarm
    now = datetime.now(timezone.utc)
    cur = _active(db, dependent_id, now)
    if cur is not None:
        out = _out(db, cur, now, already=True)
        db.rollback()
        return out, False
    s = get_settings()
    d = duration_s or s.ALARM_DEFAULT_S
    alarm_id = uuid.uuid4()
    name = notification_service._display_name(db, dependent_id)
    db.add(AuditLog(actor_id=user.user_id, action="remote_alarm_triggered", target_type="dependent", target_id=dependent_id))
    n = notification_service.notify(  # commits
        db, dependent_id, START, CRITICAL, "Alarm", "Your Guardian is sounding the alarm to find you.",
        dependent_id=dependent_id, dedupe_key=f"{alarm_id}:start",
        extra={"alarm_id": str(alarm_id), "duration_s": d, "expires_at": (now + timedelta(seconds=d)).isoformat(), "triggered_by": str(user.user_id)},
    )
    return _out(db, n, now), True


def status(db: Session, user: User, dependent_id: uuid.UUID) -> AlarmStatusOut:
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    else:
        _require_primary(db, user, dependent_id)
    now = datetime.now(timezone.utc)
    cur = _active(db, dependent_id, now)
    return AlarmStatusOut(active=cur is not None, alarm=_out(db, cur, now) if cur else None)


def stop(db: Session, user: User, dependent_id: uuid.UUID) -> AlarmOut:
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    else:
        _require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    now = datetime.now(timezone.utc)
    cur = _active(db, dependent_id, now)
    if cur is None:
        db.rollback()
        raise AppError(409, "NO_ACTIVE_ALARM", "No alarm is sounding.")
    p = cur.payload
    db.add(AuditLog(actor_id=user.user_id, action="remote_alarm_stopped", target_type="dependent", target_id=dependent_id))
    notification_service.notify(  # commits; the phone stops the sound
        db, dependent_id, STOP, CRITICAL, "Alarm stopped", "The alarm has been stopped.", dependent_id=dependent_id,
        dedupe_key=f"{p['alarm_id']}:stop", extra={"alarm_id": p["alarm_id"]},
    )
    db.expire_all()
    return _out(db, _start_row(db, dependent_id, p["alarm_id"]), now)
