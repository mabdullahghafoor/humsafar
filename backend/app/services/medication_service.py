"""
Medication scheduling and dual confirmation (Task 3.2, FR-F1).

Schedules   A Guardian (Primary, or a Secondary with 'medication_management') writes a schedule: drug, dosage,
            one or more times a day, daily or on chosen weekdays. One database row per dose time (SDS 9.2).
            Times are local clock times in MEDICATION_TIMEZONE (default Asia/Karachi). Removing a schedule only
            switches it off, so the dose history stays for the analytics (FR-Q1).
Doses       A background job (every minute) creates one `medication_confirmations` row per due dose, starting
            MEDICATION_REMIND_BEFORE_S (15 min) before the dose time, and tells the Dependent:
               before the time  -> a standard reminder
               at the time      -> a critical "time to take it" alert (only while the dose is not yet confirmed)
            Each message has a dedupe key, so running the job twice, or in two processes, never sends it twice.
Confirming  Two steps, by the Dependent only (so a wrong tap does not mark a dose as taken):
               1. confirm-request -> the server answers with a short-lived token tied to that one dose
               2. confirm         -> sending the token marks the dose 'taken'
            Step 2 is idempotent: a second call keeps the first time and says already_confirmed.
Not here    Marking a dose 'missed' and raising the alert for it is Task 3.3 (FR-D1). The window is exposed now
            (`window_ends_at`) so the app can show it.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import MED_CONFIRM, create_confirm_token, decode_token
from app.models import AuditLog, DependentProfile, EscalationEvent, MedicationConfirmation, MedicationSchedule, Notification, User
from app.schemas.medication import (
    DAYS,
    ConfirmOut,
    ConfirmRequestOut,
    DoseListOut,
    DoseOut,
    EscalateOut,
    MedicationIn,
    MedicationListOut,
    MedicationOut,
    MedicationUpdate,
)
from app.services import linkage_service, notification_service, permission_service

PENDING, TAKEN, MISSED = "pending", "taken", "missed"
MODULE = "medication_management"


# ------------------------------------------------------------------ frequency text <-> days

def encode_frequency(frequency: str, days: list[str] | None) -> str:
    if frequency == "daily":
        return "daily"
    return "weekly:" + ",".join(d for d in DAYS if d in set(days or []))


def decode_frequency(text_value: str) -> tuple[str, list[str] | None]:
    if text_value.startswith("weekly:"):
        return "weekly", [d for d in text_value[7:].split(",") if d]
    return "daily", None


def applies_on(frequency_text: str, day: date) -> bool:
    freq, days = decode_frequency(frequency_text)
    return freq == "daily" or DAYS[day.weekday()] in (days or [])


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().MEDICATION_TIMEZONE)


def occurrence(day: date, t: dtime) -> datetime:
    """The UTC moment of local time `t` on local date `day`."""
    return datetime.combine(day, t.replace(tzinfo=None), tzinfo=tz()).astimezone(timezone.utc)


def window_end(due: datetime) -> datetime:
    return due + timedelta(seconds=get_settings().MEDICATION_WINDOW_S)


def deadline(c: MedicationConfirmation) -> datetime:
    """When this dose counts as missed: the normal window, or later if a Guardian gave more time."""
    return c.extended_until or window_end(c.scheduled_for)


# ------------------------------------------------------------------ access

def authorize_read(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    """The Dependent sees their own medicines; Guardians need 'medication_management' (Primary always)."""
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return
    permission_service.check_module_access(db, user, dependent_id, MODULE)


def require_self_dependent(user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "Only the Dependent can do this.")


def _audit(db: Session, user: User, action: str, target_type: str, target_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=user.user_id, action=action, target_type=target_type, target_id=target_id))


# ------------------------------------------------------------------ schedules

def _out(s: MedicationSchedule) -> MedicationOut:
    freq, days = decode_frequency(s.frequency)
    return MedicationOut(
        schedule_id=s.schedule_id,
        dependent_id=s.dependent_id,
        drug_name=s.drug_name,
        dosage=s.dosage,
        time=s.time_of_day.strftime("%H:%M"),
        frequency=freq,
        days=days,
        active=s.active,
        created_by=s.created_by,
        created_at=s.created_at,
    )


def _drop_future_pending(db: Session, schedule_id: uuid.UUID, now: datetime) -> None:
    """After a time change or switch-off, doses that were prepared but are not due yet no longer apply."""
    db.execute(
        delete(MedicationConfirmation).where(
            MedicationConfirmation.schedule_id == schedule_id,
            MedicationConfirmation.status == PENDING,
            MedicationConfirmation.scheduled_for > now,
        )
    )


def create(db: Session, user: User, dependent_id: uuid.UUID, body: MedicationIn) -> MedicationListOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)  # so two requests cannot both squeeze under the cap
    cap = get_settings().MEDICATION_MAX_ACTIVE_SCHEDULES
    active_now = db.scalars(
        select(MedicationSchedule.schedule_id).where(
            MedicationSchedule.dependent_id == dependent_id, MedicationSchedule.active.is_(True)
        )
    ).all()
    if len(active_now) + len(body.times) > cap:
        db.rollback()
        raise AppError(409, "MEDICATION_LIMIT_REACHED", f"At most {cap} active dose times per Dependent.", {"limit": cap})
    freq = encode_frequency(body.frequency, body.days)
    rows = []
    for hhmm in body.times:
        h, m = hhmm.split(":")
        row = MedicationSchedule(
            dependent_id=dependent_id,
            drug_name=body.drug_name,
            dosage=body.dosage,
            time_of_day=dtime(int(h), int(m)),
            frequency=freq,
            created_by=user.user_id,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    for row in rows:
        _audit(db, user, "medication_schedule_created", "medication_schedule", row.schedule_id)
    db.commit()
    for row in rows:
        db.refresh(row)
    return MedicationListOut(timezone=get_settings().MEDICATION_TIMEZONE, items=[_out(r) for r in rows])


def list_schedules(db: Session, user: User, dependent_id: uuid.UUID, include_inactive: bool = False) -> MedicationListOut:
    authorize_read(db, user, dependent_id)
    q = select(MedicationSchedule).where(MedicationSchedule.dependent_id == dependent_id)
    if not include_inactive:
        q = q.where(MedicationSchedule.active.is_(True))
    rows = db.scalars(q.order_by(MedicationSchedule.time_of_day, MedicationSchedule.drug_name)).all()
    return MedicationListOut(timezone=get_settings().MEDICATION_TIMEZONE, items=[_out(r) for r in rows])


def _get_schedule(db: Session, dependent_id: uuid.UUID, schedule_id: uuid.UUID, lock: bool = False) -> MedicationSchedule:
    q = select(MedicationSchedule).where(
        MedicationSchedule.schedule_id == schedule_id, MedicationSchedule.dependent_id == dependent_id
    )
    if lock:
        q = q.with_for_update()
    s = db.scalar(q)
    if s is None:
        raise AppError(404, "MEDICATION_NOT_FOUND", "Medication schedule not found.")
    return s


def update_schedule(
    db: Session, user: User, dependent_id: uuid.UUID, schedule_id: uuid.UUID, body: MedicationUpdate
) -> MedicationOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    s = _get_schedule(db, dependent_id, schedule_id, lock=True)
    freq, days = decode_frequency(s.frequency)
    new_freq = body.frequency or freq
    new_days = body.days if body.days is not None else days
    if body.frequency == "daily":
        if body.days:
            raise AppError(422, "VALIDATION_ERROR", "days is only used when frequency is 'weekly'.")
        new_days = None
    if new_freq == "weekly" and not new_days:
        raise AppError(422, "VALIDATION_ERROR", "days is required when frequency is 'weekly'.")
    if new_freq == "daily" and body.days:
        raise AppError(422, "VALIDATION_ERROR", "days is only used when frequency is 'weekly'.")
    changed_timing = False
    if body.drug_name is not None:
        s.drug_name = body.drug_name
    if body.dosage is not None:
        s.dosage = body.dosage
    if body.time is not None:
        h, m = body.time.split(":")
        t = dtime(int(h), int(m))
        changed_timing |= t != s.time_of_day
        s.time_of_day = t
    enc = encode_frequency(new_freq, new_days)
    changed_timing |= enc != s.frequency
    s.frequency = enc
    if body.active is not None:
        changed_timing |= body.active != s.active
        s.active = body.active
    if changed_timing:
        _drop_future_pending(db, s.schedule_id, datetime.now(timezone.utc))
    _audit(db, user, "medication_schedule_updated", "medication_schedule", s.schedule_id)
    db.commit()
    db.refresh(s)
    return _out(s)


def deactivate(db: Session, user: User, dependent_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    s = _get_schedule(db, dependent_id, schedule_id, lock=True)
    if s.active:
        s.active = False
        _drop_future_pending(db, s.schedule_id, datetime.now(timezone.utc))
        _audit(db, user, "medication_schedule_deactivated", "medication_schedule", s.schedule_id)
    db.commit()


# ------------------------------------------------------------------ doses

def _dose_out(c: MedicationConfirmation, s: MedicationSchedule, alert_tier: str | None = None) -> DoseOut:
    return DoseOut(
        confirmation_id=c.confirmation_id,
        schedule_id=c.schedule_id,
        drug_name=s.drug_name,
        dosage=s.dosage,
        scheduled_for=c.scheduled_for,
        status=c.status,
        confirmed_at=c.confirmed_at,
        window_ends_at=deadline(c),
        open_alert_tier=alert_tier,
    )


def list_doses(
    db: Session,
    user: User,
    dependent_id: uuid.UUID,
    start: datetime | None,
    end: datetime | None,
    status: str | None,
    limit: int = 200,
) -> DoseListOut:
    authorize_read(db, user, dependent_id)
    now = datetime.now(timezone.utc)
    start = start or now - timedelta(hours=24)
    end = end or now + timedelta(hours=24)
    if end < start:
        raise AppError(422, "VALIDATION_ERROR", "'to' must not be before 'from'.")
    if end - start > timedelta(days=31):
        raise AppError(422, "VALIDATION_ERROR", "Ask for at most 31 days at a time.")
    q = (
        select(MedicationConfirmation, MedicationSchedule)
        .join(MedicationSchedule, MedicationSchedule.schedule_id == MedicationConfirmation.schedule_id)
        .where(
            MedicationSchedule.dependent_id == dependent_id,
            MedicationConfirmation.scheduled_for >= start,
            MedicationConfirmation.scheduled_for <= end,
        )
    )
    if status:
        q = q.where(MedicationConfirmation.status == status)
    rows = db.execute(q.order_by(MedicationConfirmation.scheduled_for).limit(limit)).all()
    tiers = dict(
        db.execute(
            select(EscalationEvent.reference_id, EscalationEvent.tier).where(
                EscalationEvent.reference_id.in_([c.confirmation_id for c, _ in rows]),
                EscalationEvent.trigger_type == "missed_dose",
                EscalationEvent.status == "open",
            )
        ).all()
    )
    return DoseListOut(items=[_dose_out(c, s, tiers.get(c.confirmation_id)) for c, s in rows])


def _find_dose(
    db: Session, user: User, schedule_id: uuid.UUID, confirmation_id: uuid.UUID | None
) -> tuple[MedicationConfirmation, MedicationSchedule]:
    s = db.get(MedicationSchedule, schedule_id)
    if s is None or s.dependent_id != user.user_id:
        # Same answer for "does not exist" and "belongs to someone else": nothing is leaked.
        raise AppError(404, "MEDICATION_NOT_FOUND", "Medication schedule not found.")
    q = select(MedicationConfirmation).where(MedicationConfirmation.schedule_id == schedule_id)
    if confirmation_id is not None:
        q = q.where(MedicationConfirmation.confirmation_id == confirmation_id)
    else:
        q = q.where(MedicationConfirmation.status != TAKEN)
    c = db.scalars(q.order_by(MedicationConfirmation.scheduled_for.desc())).first()
    if c is None:
        raise AppError(404, "NO_DOSE_DUE", "There is no dose waiting to be confirmed.")
    return c, s


def confirm_request(
    db: Session, user: User, dependent_id: uuid.UUID, schedule_id: uuid.UUID, confirmation_id: uuid.UUID | None
) -> ConfirmRequestOut:
    """Step 1."""
    require_self_dependent(user, dependent_id)
    c, s = _find_dose(db, user, schedule_id, confirmation_id)
    if c.status == TAKEN:
        raise AppError(409, "DOSE_ALREADY_CONFIRMED", "This dose is already marked as taken.")
    secs = get_settings().MEDICATION_CONFIRM_TOKEN_S
    return ConfirmRequestOut(
        confirmation_id=c.confirmation_id,
        drug_name=s.drug_name,
        dosage=s.dosage,
        scheduled_for=c.scheduled_for,
        confirm_token=create_confirm_token(user.user_id, c.confirmation_id, secs),
        expires_in_s=secs,
    )


def confirm(
    db: Session, user: User, dependent_id: uuid.UUID, schedule_id: uuid.UUID, token: str
) -> ConfirmOut:
    """Step 2. Safe to repeat: the first confirmation time is kept."""
    require_self_dependent(user, dependent_id)
    try:
        claims = decode_token(token, MED_CONFIRM)
    except AppError as e:
        code = "CONFIRM_TOKEN_EXPIRED" if e.code == "TOKEN_EXPIRED" else "CONFIRM_TOKEN_INVALID"
        raise AppError(400, code, "This confirmation has expired. Start again." if code.endswith("EXPIRED") else "Invalid confirmation.")
    try:
        dose_id = uuid.UUID(claims["dose"])
    except (KeyError, ValueError):
        raise AppError(400, "CONFIRM_TOKEN_INVALID", "Invalid confirmation.")
    if claims.get("sub") != str(user.user_id):
        raise AppError(400, "CONFIRM_TOKEN_INVALID", "Invalid confirmation.")
    c, _s = _find_dose(db, user, schedule_id, dose_id)
    if c.confirmation_id != dose_id:
        raise AppError(400, "CONFIRM_TOKEN_INVALID", "Invalid confirmation.")

    now = datetime.now(timezone.utc)
    # One atomic statement: only one of several simultaneous calls changes the row.
    won = db.execute(
        update(MedicationConfirmation)
        .where(MedicationConfirmation.confirmation_id == dose_id, MedicationConfirmation.status != TAKEN)
        .values(status=TAKEN, confirmed_at=now)
        .returning(MedicationConfirmation.confirmation_id)
    ).scalar()
    if won is not None:
        _audit(db, user, "medication_dose_confirmed", "medication_confirmation", dose_id)
        _close_missed_alert(db, dose_id, now)  # a late "taken" closes the Guardians' alert (clarification 38)
    db.commit()
    if won is not None:
        notification_service.dispatch_events_safely(db, user.user_id)  # sends the "all clear" at once
    db.expire_all()
    c = db.get(MedicationConfirmation, dose_id)
    return ConfirmOut(
        confirmation_id=c.confirmation_id,
        schedule_id=c.schedule_id,
        status=c.status,
        confirmed_at=c.confirmed_at,
        already_confirmed=won is None,
    )


# ------------------------------------------------------------------ background job (every minute)

def tick(db: Session, now: datetime | None = None) -> int:
    """
    Prepare doses and send reminders. Returns how many notifications were created.
    Looks at doses due from 24 h ago until REMIND_BEFORE from now, so a restart after downtime catches up
    (a dose row is created even if its window has passed; Task 3.3 turns those into 'missed').
    """
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    local_today = now.astimezone(tz()).date()
    lead = timedelta(seconds=s.MEDICATION_REMIND_BEFORE_S)
    sent = 0
    schedules = db.scalars(
        select(MedicationSchedule).where(
            MedicationSchedule.active.is_(True),
            # only people whose account is active: the Dependent profile must exist
            MedicationSchedule.dependent_id.in_(select(DependentProfile.user_id)),
        )
    ).all()
    for sch in schedules:
        for offset in (-1, 0, 1):
            day = local_today + timedelta(days=offset)
            if not applies_on(sch.frequency, day):
                continue
            due = occurrence(day, sch.time_of_day)
            if due < sch.created_at or due < now - timedelta(hours=24) or due - lead > now:
                continue  # before the schedule existed, too old, or not yet time to prepare
            db.execute(
                pg_insert(MedicationConfirmation)
                .values(confirmation_id=uuid.uuid4(), schedule_id=sch.schedule_id, scheduled_for=due, status=PENDING)
                .on_conflict_do_nothing(constraint="uq_confirmation_schedule_dose")
            )
            db.commit()
            dose = db.scalar(
                select(MedicationConfirmation).where(
                    MedicationConfirmation.schedule_id == sch.schedule_id, MedicationConfirmation.scheduled_for == due
                )
            )
            if dose is None or dose.status == TAKEN:
                continue
            extra = {
                "schedule_id": str(sch.schedule_id),
                "confirmation_id": str(dose.confirmation_id),
                "scheduled_for": due.isoformat(),
                "drug_name": sch.drug_name,
                "dosage": sch.dosage,
            }
            key = f"{sch.schedule_id}:{due.isoformat()}"
            if now < due:
                n = notification_service.notify(
                    db, sch.dependent_id, "medication_reminder", notification_service.STANDARD,
                    "Medicine soon", f"{sch.drug_name} ({sch.dosage}) is due at {due.astimezone(tz()):%H:%M}.",
                    dependent_id=sch.dependent_id, dedupe_key=f"med-remind:{key}", extra=extra,
                )
            elif now <= deadline(dose):
                n = notification_service.notify(
                    db, sch.dependent_id, "medication_due", notification_service.CRITICAL,
                    "Time for your medicine", f"Take {sch.drug_name} ({sch.dosage}) now, then confirm in the app.",
                    dependent_id=sch.dependent_id, dedupe_key=f"med-due:{key}", extra=extra,
                )
            else:
                n = None
            sent += 1 if n else 0
    return sent


# ------------------------------------------------------------------ missed doses (Task 3.3, FR-D1)

def _close_missed_alert(db: Session, dose_id: uuid.UUID, now: datetime) -> None:
    """Resolve the open missed-dose alert of one dose, if any. Does not commit."""
    db.execute(
        update(EscalationEvent)
        .where(
            EscalationEvent.reference_id == dose_id,
            EscalationEvent.trigger_type == "missed_dose",
            EscalationEvent.status == "open",
        )
        .values(status="resolved", resolved_at=now)
    )


def sweep_missed(db: Session, now: datetime | None = None) -> int:
    """
    Background job (every minute). A dose still `pending` after its deadline becomes `missed`, and an open
    `missed_dose` alert (tier primary) is created for it; notification_service tells the Primary Guardian.
    Returns how many alerts were opened.
      * Only one process can win the pending -> missed change, so there is one alert per missed dose.
      * A schedule that was switched off, or a dose found missed long after the fact (server was down,
        MEDICATION_MISSED_ALERT_MAX_AGE_S), is marked missed WITHOUT an alert.
    """
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    limit = func.coalesce(
        MedicationConfirmation.extended_until,
        MedicationConfirmation.scheduled_for + timedelta(seconds=s.MEDICATION_WINDOW_S),
    )
    due = db.execute(
        select(MedicationConfirmation.confirmation_id, MedicationSchedule.dependent_id, MedicationSchedule.active, limit)
        .join(MedicationSchedule, MedicationSchedule.schedule_id == MedicationConfirmation.schedule_id)
        .where(MedicationConfirmation.status == PENDING, limit < now)
    ).all()
    opened = 0
    for cid, dep_id, active, end in due:
        won = db.execute(
            update(MedicationConfirmation)
            .where(MedicationConfirmation.confirmation_id == cid, MedicationConfirmation.status == PENDING, limit < now)
            .values(status=MISSED)
            .returning(MedicationConfirmation.confirmation_id)
        ).scalar()
        if won is not None and active and end >= now - timedelta(seconds=s.MEDICATION_MISSED_ALERT_MAX_AGE_S):
            res = db.execute(
                pg_insert(EscalationEvent)
                .values(dependent_id=dep_id, trigger_type="missed_dose", tier="primary", status="open", reference_id=cid)
                .on_conflict_do_nothing()
                .returning(EscalationEvent.event_id)
            ).scalar()
            opened += res is not None
        db.commit()
    return opened


def _dose_for_guardian(db: Session, dependent_id: uuid.UUID, confirmation_id: uuid.UUID):
    row = db.execute(
        select(MedicationConfirmation, MedicationSchedule)
        .join(MedicationSchedule, MedicationSchedule.schedule_id == MedicationConfirmation.schedule_id)
        .where(MedicationConfirmation.confirmation_id == confirmation_id, MedicationSchedule.dependent_id == dependent_id)
        .with_for_update(of=MedicationConfirmation)
    ).first()
    if row is None:
        raise AppError(404, "DOSE_NOT_FOUND", "Dose not found.")
    return row


def extend(db: Session, user: User, dependent_id: uuid.UUID, confirmation_id: uuid.UUID, minutes: int) -> DoseOut:
    """
    FR-D1 option 1: give the Dependent more time. The new deadline is `minutes` after the current deadline, or
    after now if that has passed. A missed dose goes back to pending and its alert closes (the Guardians get an
    all-clear); the Dependent gets a critical "please take it" alert. Missing it again raises a new alert.
    """
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)
    c, sch = _dose_for_guardian(db, dependent_id, confirmation_id)
    if c.status == TAKEN:
        db.rollback()
        raise AppError(409, "DOSE_ALREADY_CONFIRMED", "This dose is already marked as taken.")
    now = datetime.now(timezone.utc)
    c.extended_until = max(deadline(c), now) + timedelta(minutes=minutes)
    c.status = PENDING
    _close_missed_alert(db, c.confirmation_id, now)
    _audit(db, user, "medication_dose_extended", "medication_confirmation", c.confirmation_id)
    db.commit()
    db.refresh(c)
    local = c.extended_until.astimezone(tz())
    notification_service.notify(
        db, sch.dependent_id, "medication_extended", notification_service.CRITICAL,
        "More time for your medicine",
        f"Please take {sch.drug_name} ({sch.dosage}) by {local:%H:%M}, then confirm in the app.",
        dependent_id=sch.dependent_id, dedupe_key=f"med-extend:{c.confirmation_id}:{c.extended_until.isoformat()}",
        extra={
            "schedule_id": str(sch.schedule_id), "confirmation_id": str(c.confirmation_id),
            "scheduled_for": c.scheduled_for.isoformat(), "drug_name": sch.drug_name, "dosage": sch.dosage,
        },
    )
    notification_service.dispatch_events_safely(db, dependent_id)
    return _dose_out(c, sch)


def escalate(db: Session, user: User, dependent_id: uuid.UUID, confirmation_id: uuid.UUID) -> EscalateOut:
    """
    FR-D1 option 2: trigger further escalation now, without waiting. Moves the open missed-dose alert from the
    Primary to the Secondary level and alerts the Secondaries who may see alerts. (The automatic timeouts and
    the external-contact step come with the escalation engine, Task 3.5 and 3.8.)
    """
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)
    _dose_for_guardian(db, dependent_id, confirmation_id)
    ev = db.scalar(
        select(EscalationEvent)
        .where(
            EscalationEvent.reference_id == confirmation_id,
            EscalationEvent.trigger_type == "missed_dose",
            EscalationEvent.status == "open",
        )
        .with_for_update()
    )
    if ev is None:
        db.rollback()
        raise AppError(409, "NO_OPEN_ALERT", "There is no open missed-dose alert for this dose.")
    if ev.tier != "primary":
        db.rollback()
        raise AppError(409, "ALREADY_ESCALATED", "This alert has already been escalated.")
    ev.tier = "secondary"
    ev.tier_changed_at = datetime.now(timezone.utc)  # the Secondary timer (Task 3.5) starts now
    _audit(db, user, "medication_alert_escalated", "escalation_event", ev.event_id)
    db.commit()
    notification_service.dispatch_events(db, dependent_id)
    told = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.payload["dedupe_key"].astext == f"{ev.event_id}:secondary:open"
        )
    )
    return EscalateOut(confirmation_id=confirmation_id, event_id=ev.event_id, tier="secondary", notified=told or 0)
