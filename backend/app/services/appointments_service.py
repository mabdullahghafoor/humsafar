"""
Appointment tracker (Task 5.1, FR-G4).

- Who: the Dependent (own appointments) or a Guardian with `health_records` (Primary always) can add, change,
  cancel and delete. Same gate as the Medical Vault.
- Past times are refused: an appointment is something still to come.
- Telling people: everyone else involved gets a standard `appointment_update` notification when one is added,
  moved or cancelled. Reminders (`appointment_reminder`) go to the Dependent and to each Guardian who may see
  appointments, 24 h and 1 h before (APPOINTMENT_REMIND_LEADS_S). A reminder is skipped if the appointment was
  made after that moment (nobody needs "24 h to go" for an appointment booked 3 h ahead). Only the closest
  reminder is sent after downtime. A moved appointment gets its reminders again.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Appointment, AuditLog, DependentProfile, User
from app.schemas.appointment import AppointmentIn, AppointmentList, AppointmentOut, AppointmentUpdate
from app.services import linkage_service
from app.services import notification_service as ns
from app.services.records_service import authorize

log = logging.getLogger("humsafar.appointments")


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().APPOINTMENT_TIMEZONE)


def _when(dt: datetime) -> str:
    return dt.astimezone(_tz()).strftime("%a %d %b, %H:%M")


def _leads() -> list[int]:
    out = []
    for part in get_settings().APPOINTMENT_REMIND_LEADS_S.split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            out.append(int(part))
    return sorted(set(out), reverse=True)


def _audit(db: Session, user: User, action: str, a: Appointment) -> None:
    db.add(AuditLog(actor_id=user.user_id, action=action, target_type="appointment", target_id=a.appointment_id))


def _out(a: Appointment, names: dict, now: datetime) -> AppointmentOut:
    return AppointmentOut(
        appointment_id=a.appointment_id, dependent_id=a.dependent_id, provider_name=a.provider_name,
        scheduled_at=a.scheduled_at, notes=a.notes, status=a.status, created_by=a.created_by,
        created_by_name=names.get(a.created_by), created_at=a.created_at,
        is_upcoming=a.status == "scheduled" and a.scheduled_at > now,
    )


def _outs(db: Session, rows: list[Appointment]) -> list[AppointmentOut]:
    ids = {a.created_by for a in rows}
    names = {u.user_id: (u.full_name or "").strip() or None for u in db.scalars(select(User).where(User.user_id.in_(ids)))} if ids else {}
    now = datetime.now(timezone.utc)
    return [_out(a, names, now) for a in rows]


def _audience(db: Session, dependent_id: uuid.UUID) -> list[uuid.UUID]:
    """The Dependent first, then every Guardian who may see appointments."""
    return [dependent_id] + ns.recipients(db, dependent_id, ns.LINKED_PERMITTED, module="health_records")


def _tell_others(db: Session, actor: User, a: Appointment, title: str, what: str) -> None:
    name = ns._display_name(db, a.dependent_id)
    for uid in _audience(db, a.dependent_id):
        if uid == actor.user_id:
            continue
        who = "Your" if uid == a.dependent_id else f"{name}'s"
        ns.notify(
            db, uid, "appointment_update", ns.STANDARD, title, f"{who} appointment with {a.provider_name} {what}.",
            dependent_id=a.dependent_id,
            extra={"appointment_id": str(a.appointment_id), "scheduled_at": a.scheduled_at.isoformat(), "provider_name": a.provider_name},
        )


def _future(when: datetime) -> None:
    if when <= datetime.now(timezone.utc):
        raise AppError(422, "APPOINTMENT_IN_PAST", "The appointment time must be in the future.")


# ------------------------------------------------------------------ CRUD

def create(db: Session, user: User, dependent_id: uuid.UUID, body: AppointmentIn) -> AppointmentOut:
    authorize(db, user, dependent_id)
    _future(body.scheduled_at)
    linkage_service._lock_dependent(db, dependent_id)  # so two requests cannot both squeeze under the cap or both add the same one
    now = datetime.now(timezone.utc)
    open_q = select(Appointment).where(Appointment.dependent_id == dependent_id, Appointment.status == "scheduled", Appointment.scheduled_at > now)
    open_rows = list(db.scalars(open_q))
    if any(a.scheduled_at == body.scheduled_at and a.provider_name.lower() == body.provider_name.lower() for a in open_rows):
        raise AppError(409, "APPOINTMENT_EXISTS", "This appointment is already scheduled.")
    if len(open_rows) >= get_settings().APPOINTMENT_MAX_OPEN:
        raise AppError(409, "APPOINTMENTS_LIMIT", f"There are already {get_settings().APPOINTMENT_MAX_OPEN} appointments to come.")
    a = Appointment(
        dependent_id=dependent_id, provider_name=body.provider_name, scheduled_at=body.scheduled_at, notes=body.notes,
        created_by=user.user_id, status="scheduled", time_set_at=now,
    )
    db.add(a)
    db.flush()
    _audit(db, user, "appointment_added", a)
    db.commit()
    db.refresh(a)
    _tell_others(db, user, a, "New appointment", f"is set for {_when(a.scheduled_at)}")
    return _outs(db, [a])[0]


def list_appointments(
    db: Session, user: User, dependent_id: uuid.UUID, *, when: str, limit: int, offset: int
) -> AppointmentList:
    authorize(db, user, dependent_id)
    now = datetime.now(timezone.utc)
    where = [Appointment.dependent_id == dependent_id]
    if when == "upcoming":
        where += [Appointment.status == "scheduled", Appointment.scheduled_at > now]
        order = (Appointment.scheduled_at.asc(), Appointment.appointment_id)
    elif when == "past":
        where += [(Appointment.status == "cancelled") | (Appointment.scheduled_at <= now)]
        order = (Appointment.scheduled_at.desc(), Appointment.appointment_id)
    else:
        order = (Appointment.scheduled_at.desc(), Appointment.appointment_id)
    total = db.scalar(select(func.count()).select_from(Appointment).where(*where))
    rows = list(db.scalars(select(Appointment).where(*where).order_by(*order).limit(limit).offset(offset)))
    return AppointmentList(items=_outs(db, rows), total=total, limit=limit, offset=offset)


def _get(db: Session, user: User, dependent_id: uuid.UUID, appointment_id: uuid.UUID, *, lock: bool = False) -> Appointment:
    authorize(db, user, dependent_id)
    q = select(Appointment).where(Appointment.appointment_id == appointment_id, Appointment.dependent_id == dependent_id)
    a = db.scalar(q.with_for_update() if lock else q)
    if a is None:
        raise AppError(404, "APPOINTMENT_NOT_FOUND", "Appointment not found.")
    return a


def get_one(db: Session, user: User, dependent_id: uuid.UUID, appointment_id: uuid.UUID) -> AppointmentOut:
    return _outs(db, [_get(db, user, dependent_id, appointment_id)])[0]


def update(db: Session, user: User, dependent_id: uuid.UUID, appointment_id: uuid.UUID, body: AppointmentUpdate) -> AppointmentOut:
    a = _get(db, user, dependent_id, appointment_id, lock=True)
    if a.status == "cancelled":
        db.rollback()
        raise AppError(409, "APPOINTMENT_CANCELLED", "A cancelled appointment cannot be changed. Add a new one.")
    fields = body.model_fields_set
    moved = False
    if "scheduled_at" in fields and body.scheduled_at != a.scheduled_at:
        if body.scheduled_at <= datetime.now(timezone.utc):
            db.rollback()
            raise AppError(422, "APPOINTMENT_IN_PAST", "The appointment time must be in the future.")
        a.scheduled_at = body.scheduled_at
        a.time_set_at = datetime.now(timezone.utc)
        moved = True
    if "provider_name" in fields:
        a.provider_name = body.provider_name
    if "notes" in fields:
        a.notes = body.notes
    _audit(db, user, "appointment_changed", a)
    db.commit()
    db.refresh(a)
    if moved:
        _tell_others(db, user, a, "Appointment moved", f"is now {_when(a.scheduled_at)}")
    return _outs(db, [a])[0]


def cancel(db: Session, user: User, dependent_id: uuid.UUID, appointment_id: uuid.UUID) -> AppointmentOut:
    a = _get(db, user, dependent_id, appointment_id, lock=True)
    if a.status == "scheduled":
        a.status = "cancelled"
        _audit(db, user, "appointment_cancelled", a)
        db.commit()
        db.refresh(a)
        _tell_others(db, user, a, "Appointment cancelled", f"on {_when(a.scheduled_at)} was cancelled")
    else:
        db.rollback()
    return _outs(db, [a])[0]


def delete(db: Session, user: User, dependent_id: uuid.UUID, appointment_id: uuid.UUID) -> None:
    a = _get(db, user, dependent_id, appointment_id, lock=True)
    db.delete(a)
    db.add(AuditLog(actor_id=user.user_id, action="appointment_deleted", target_type="appointment", target_id=appointment_id))
    db.commit()


# ------------------------------------------------------------------ reminders (background job, every minute)

def tick(db: Session, now: datetime | None = None) -> int:
    """Send the reminders that are due. Returns how many notifications were created."""
    leads = _leads()
    if not leads:
        return 0
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(Appointment).where(
            Appointment.status == "scheduled",
            Appointment.scheduled_at > now,
            Appointment.scheduled_at <= now + timedelta(seconds=max(leads)),
            Appointment.dependent_id.in_(select(DependentProfile.user_id)),
        ).order_by(Appointment.scheduled_at)
    ).all()
    sent = 0
    for a in rows:
        due = [L for L in leads if a.scheduled_at - timedelta(seconds=L) <= now and a.time_set_at <= a.scheduled_at - timedelta(seconds=L)]
        if not due:
            continue
        lead = min(due)  # after downtime, only the closest reminder
        name = ns._display_name(db, a.dependent_id)
        when = _when(a.scheduled_at)
        for uid in _audience(db, a.dependent_id):
            body = (f"You have an appointment with {a.provider_name} at {when}." if uid == a.dependent_id
                    else f"{name} has an appointment with {a.provider_name} at {when}.")
            n = ns.notify(
                db, uid, "appointment_reminder", ns.STANDARD, "Appointment reminder", body, dependent_id=a.dependent_id,
                dedupe_key=f"appt-remind:{a.appointment_id}:{lead}:{a.scheduled_at.isoformat()}",
                extra={"appointment_id": str(a.appointment_id), "scheduled_at": a.scheduled_at.isoformat(), "provider_name": a.provider_name, "lead_s": lead},
            )
            sent += 1 if n else 0
    return sent
