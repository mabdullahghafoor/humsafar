"""
Guardian Wellness Check (Task 3.4, FR-D4).

Schedule    A Guardian (Primary, or a Secondary with 'emergency_alerts') sets up to 3 daily check times and a grace
            period (5 to 180 min, default 30). Times are local clock times in WELLNESS_TIMEZONE (Asia/Karachi).
            "Use the default schedule" creates 08:00, 14:00 and 20:00 (SRS: a default schedule, editable).
Prompt      At each check time a background job creates one `wellness_check_responses` row (status `pending`) and sends
            the Dependent a critical "Are you OK?" notification. One prompt per check per time, even with several
            processes (unique constraint).
Answer      The Dependent taps "I'm OK": POST /wellness-checks/{response_id}/respond. Safe to repeat.
Grace       When the grace period ends without an answer, the job looks at recent DEVICE ACTIVITY before escalating:
              a location fix in the last WELLNESS_ACTIVITY_WINDOW_S (30 min)  -> status `device_active`, nobody alerted
              no recent fix                                                  -> status `escalated`, an open
                                                                               `wellness_check` event at the Primary
                                                                               level (reference = the response)
            notification_service then alerts the Primary Guardian. The timers that move it up the chain are Task 3.5.
Late answer A late "I'm OK" closes the alert and sends the all-clear to everyone who was told.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AuditLog,
    DependentProfile,
    EscalationEvent,
    LocationLog,
    User,
    WellnessCheckResponse,
    WellnessCheckSchedule,
)
from app.schemas.wellness import (
    DEFAULT_GRACE_MIN,
    DEFAULT_TIMES,
    CheckResponseListOut,
    CheckResponseOut,
    RespondOut,
    WellnessIn,
    WellnessListOut,
    WellnessOut,
    WellnessUpdate,
)
from app.services import linkage_service, notification_service, permission_service

PENDING, RESPONDED, DEVICE_ACTIVE, ESCALATED, CANCELLED = "pending", "responded", "device_active", "escalated", "cancelled"
MODULE = "emergency_alerts"
EVENT = "wellness_check"


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().WELLNESS_TIMEZONE)


def occurrence(day: date, t: dtime) -> datetime:
    return datetime.combine(day, t.replace(tzinfo=None), tzinfo=tz()).astimezone(timezone.utc)


def deadline(prompted_at: datetime, grace_min: int) -> datetime:
    return prompted_at + timedelta(minutes=grace_min)


# ------------------------------------------------------------------ access

def authorize_read(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return
    permission_service.check_module_access(db, user, dependent_id, MODULE)


def _audit(db: Session, user: User, action: str, target_type: str, target_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=user.user_id, action=action, target_type=target_type, target_id=target_id))


# ------------------------------------------------------------------ schedules

def _out(w: WellnessCheckSchedule) -> WellnessOut:
    return WellnessOut(
        wc_id=w.wc_id,
        dependent_id=w.dependent_id,
        time=w.time_window.strftime("%H:%M"),
        grace_period_min=w.grace_period_min,
        active=w.active,
        created_at=w.created_at,
    )


def _active_windows(db: Session, dependent_id: uuid.UUID) -> list[WellnessCheckSchedule]:
    return list(
        db.scalars(
            select(WellnessCheckSchedule).where(
                WellnessCheckSchedule.dependent_id == dependent_id, WellnessCheckSchedule.active.is_(True)
            )
        )
    )


def _add_windows(db: Session, user: User, dependent_id: uuid.UUID, times: list[str], grace: int) -> list[WellnessCheckSchedule]:
    """Caller has checked access and holds the Dependent lock. Raises 409 on the cap or an existing time."""
    cap = get_settings().WELLNESS_MAX_WINDOWS
    existing = _active_windows(db, dependent_id)
    if len(existing) + len(times) > cap:
        db.rollback()
        raise AppError(409, "WELLNESS_LIMIT_REACHED", f"At most {cap} wellness checks per Dependent.", {"limit": cap})
    have = {w.time_window.strftime("%H:%M") for w in existing}
    clash = sorted(set(times) & have)
    if clash:
        db.rollback()
        raise AppError(409, "WELLNESS_TIME_EXISTS", "There is already a check at this time.", {"times": clash})
    rows = []
    for hhmm in times:
        h, m = hhmm.split(":")
        row = WellnessCheckSchedule(dependent_id=dependent_id, time_window=dtime(int(h), int(m)), grace_period_min=grace)
        db.add(row)
        rows.append(row)
    db.flush()
    for row in rows:
        _audit(db, user, "wellness_check_created", "wellness_check_schedule", row.wc_id)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def create(db: Session, user: User, dependent_id: uuid.UUID, body: WellnessIn) -> WellnessListOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)
    rows = _add_windows(db, user, dependent_id, body.times, body.grace_period_min)
    return _list_out([_out(r) for r in rows])


def create_default(db: Session, user: User, dependent_id: uuid.UUID) -> WellnessListOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)
    if _active_windows(db, dependent_id):
        db.rollback()
        raise AppError(409, "SCHEDULE_ALREADY_EXISTS", "This Dependent already has wellness checks. Edit them instead.")
    rows = _add_windows(db, user, dependent_id, list(DEFAULT_TIMES), DEFAULT_GRACE_MIN)
    return _list_out([_out(r) for r in rows])


def _list_out(items: list[WellnessOut]) -> WellnessListOut:
    return WellnessListOut(
        timezone=get_settings().WELLNESS_TIMEZONE,
        default_times=list(DEFAULT_TIMES),
        default_grace_period_min=DEFAULT_GRACE_MIN,
        items=items,
    )


def list_windows(db: Session, user: User, dependent_id: uuid.UUID, include_inactive: bool = False) -> WellnessListOut:
    authorize_read(db, user, dependent_id)
    q = select(WellnessCheckSchedule).where(WellnessCheckSchedule.dependent_id == dependent_id)
    if not include_inactive:
        q = q.where(WellnessCheckSchedule.active.is_(True))
    rows = db.scalars(q.order_by(WellnessCheckSchedule.time_window)).all()
    return _list_out([_out(r) for r in rows])


def _get(db: Session, dependent_id: uuid.UUID, wc_id: uuid.UUID) -> WellnessCheckSchedule:
    w = db.scalar(
        select(WellnessCheckSchedule)
        .where(WellnessCheckSchedule.wc_id == wc_id, WellnessCheckSchedule.dependent_id == dependent_id)
        .with_for_update()
    )
    if w is None:
        raise AppError(404, "WELLNESS_CHECK_NOT_FOUND", "Wellness check not found.")
    return w


def update_window(
    db: Session, user: User, dependent_id: uuid.UUID, wc_id: uuid.UUID, body: WellnessUpdate
) -> WellnessOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    linkage_service._lock_dependent(db, dependent_id)
    w = _get(db, dependent_id, wc_id)
    others = [x for x in _active_windows(db, dependent_id) if x.wc_id != w.wc_id]
    new_time = w.time_window
    if body.time is not None:
        h, m = body.time.split(":")
        new_time = dtime(int(h), int(m))
    new_active = w.active if body.active is None else body.active
    if new_active:
        if any(x.time_window == new_time for x in others):
            db.rollback()
            raise AppError(409, "WELLNESS_TIME_EXISTS", "There is already a check at this time.", {"times": [new_time.strftime("%H:%M")]})
        if not w.active and len(others) + 1 > get_settings().WELLNESS_MAX_WINDOWS:
            db.rollback()
            raise AppError(409, "WELLNESS_LIMIT_REACHED", "Too many wellness checks.", {"limit": get_settings().WELLNESS_MAX_WINDOWS})
    w.time_window = new_time
    w.active = new_active
    if body.grace_period_min is not None:
        w.grace_period_min = body.grace_period_min
    _audit(db, user, "wellness_check_updated", "wellness_check_schedule", w.wc_id)
    db.commit()
    db.refresh(w)
    return _out(w)


def deactivate(db: Session, user: User, dependent_id: uuid.UUID, wc_id: uuid.UUID) -> None:
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    w = _get(db, dependent_id, wc_id)
    if w.active:
        w.active = False
        _audit(db, user, "wellness_check_deactivated", "wellness_check_schedule", w.wc_id)
    db.commit()


# ------------------------------------------------------------------ prompts and answers

def _resp_out(r: WellnessCheckResponse, w: WellnessCheckSchedule, tier: str | None) -> CheckResponseOut:
    return CheckResponseOut(
        response_id=r.response_id,
        wc_id=r.wc_id,
        prompted_at=r.prompted_at,
        deadline=deadline(r.prompted_at, w.grace_period_min),
        status=r.status,
        responded_at=r.responded_at,
        open_alert_tier=tier,
    )


def list_responses(
    db: Session, user: User, dependent_id: uuid.UUID, start: datetime | None, end: datetime | None, status: str | None, limit: int = 200
) -> CheckResponseListOut:
    authorize_read(db, user, dependent_id)
    now = datetime.now(timezone.utc)
    start = start or now - timedelta(hours=24)
    end = end or now + timedelta(hours=1)
    if end < start:
        raise AppError(422, "VALIDATION_ERROR", "'to' must not be before 'from'.")
    if end - start > timedelta(days=31):
        raise AppError(422, "VALIDATION_ERROR", "Ask for at most 31 days at a time.")
    q = (
        select(WellnessCheckResponse, WellnessCheckSchedule)
        .join(WellnessCheckSchedule, WellnessCheckSchedule.wc_id == WellnessCheckResponse.wc_id)
        .where(
            WellnessCheckSchedule.dependent_id == dependent_id,
            WellnessCheckResponse.prompted_at >= start,
            WellnessCheckResponse.prompted_at <= end,
        )
    )
    if status:
        q = q.where(WellnessCheckResponse.status == status)
    rows = db.execute(q.order_by(WellnessCheckResponse.prompted_at).limit(limit)).all()
    tiers = dict(
        db.execute(
            select(EscalationEvent.reference_id, EscalationEvent.tier).where(
                EscalationEvent.reference_id.in_([r.response_id for r, _ in rows]),
                EscalationEvent.trigger_type == EVENT,
                EscalationEvent.status == "open",
            )
        ).all()
    )
    return CheckResponseListOut(items=[_resp_out(r, w, tiers.get(r.response_id)) for r, w in rows])


def respond(db: Session, user: User, response_id: uuid.UUID) -> RespondOut:
    """The Dependent confirms they are OK. Safe to repeat: the first time is kept."""
    if user.role != "dependent":
        raise AppError(403, "FORBIDDEN", "Only the Dependent can do this.")
    row = db.execute(
        select(WellnessCheckResponse, WellnessCheckSchedule)
        .join(WellnessCheckSchedule, WellnessCheckSchedule.wc_id == WellnessCheckResponse.wc_id)
        .where(WellnessCheckResponse.response_id == response_id)
    ).first()
    if row is None or row[1].dependent_id != user.user_id:
        raise AppError(404, "WELLNESS_CHECK_NOT_FOUND", "Wellness check not found.")  # same answer for someone else's
    now = datetime.now(timezone.utc)
    won = db.execute(
        update(WellnessCheckResponse)
        .where(WellnessCheckResponse.response_id == response_id, WellnessCheckResponse.status != RESPONDED)
        .values(status=RESPONDED, responded_at=now)
        .returning(WellnessCheckResponse.response_id)
    ).scalar()
    if won is not None:
        _audit(db, user, "wellness_check_answered", "wellness_check_response", response_id)
        db.execute(
            update(EscalationEvent)
            .where(
                EscalationEvent.reference_id == response_id,
                EscalationEvent.trigger_type == EVENT,
                EscalationEvent.status == "open",
            )
            .values(status="resolved", resolved_at=now)
        )
    db.commit()
    if won is not None:
        notification_service.dispatch_events_safely(db, user.user_id)  # the all-clear, at once
    db.expire_all()
    r = db.get(WellnessCheckResponse, response_id)
    return RespondOut(response_id=r.response_id, status=r.status, responded_at=r.responded_at, already_responded=won is None)


# ------------------------------------------------------------------ background jobs (every minute)

def tick(db: Session, now: datetime | None = None) -> int:
    """Prompt the Dependent at each check time. Returns how many prompts were created."""
    now = now or datetime.now(timezone.utc)
    local_today = now.astimezone(tz()).date()
    created = 0
    schedules = db.scalars(
        select(WellnessCheckSchedule).where(
            WellnessCheckSchedule.active.is_(True),
            WellnessCheckSchedule.dependent_id.in_(select(DependentProfile.user_id)),
        )
    ).all()
    for w in schedules:
        for offset in (-1, 0):
            due = occurrence(local_today + timedelta(days=offset), w.time_window)
            # only a check that is due, still inside its grace period, and not older than the schedule itself
            if due > now or due < w.created_at or now > deadline(due, w.grace_period_min):
                continue
            new_id = db.execute(
                pg_insert(WellnessCheckResponse)
                .values(response_id=uuid.uuid4(), wc_id=w.wc_id, prompted_at=due, status=PENDING)
                .on_conflict_do_nothing()
                .returning(WellnessCheckResponse.response_id)
            ).scalar()
            db.commit()
            if new_id is None:
                continue  # someone already prompted this one
            n = notification_service.notify(
                db, w.dependent_id, "wellness_check_prompt", notification_service.CRITICAL,
                "Are you OK?", "Please tap to confirm you are well.",
                dependent_id=w.dependent_id, dedupe_key=f"wellness-prompt:{w.wc_id}:{due.isoformat()}",
                extra={
                    "response_id": str(new_id), "wc_id": str(w.wc_id), "prompted_at": due.isoformat(),
                    "deadline": deadline(due, w.grace_period_min).isoformat(),
                },
            )
            created += 1 if n else 0
    return created


def sweep(db: Session, now: datetime | None = None) -> int:
    """
    After the grace period: cross-check recent device activity, then escalate or clear.
    Returns how many alerts were opened.
    """
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    pending = db.execute(
        select(WellnessCheckResponse, WellnessCheckSchedule)
        .join(WellnessCheckSchedule, WellnessCheckSchedule.wc_id == WellnessCheckResponse.wc_id)
        .where(WellnessCheckResponse.status == PENDING)
    ).all()
    opened = 0
    for r, w in pending:
        end = deadline(r.prompted_at, w.grace_period_min)
        if end >= now:
            continue
        stale = end < now - timedelta(seconds=s.WELLNESS_ALERT_MAX_AGE_S)
        if not w.active or stale:
            new_status = CANCELLED
        else:
            last = db.scalar(select(func.max(LocationLog.recorded_at)).where(LocationLog.dependent_id == w.dependent_id))
            recent = last is not None and last >= now - timedelta(seconds=s.WELLNESS_ACTIVITY_WINDOW_S)
            new_status = DEVICE_ACTIVE if recent else ESCALATED
        won = db.execute(
            update(WellnessCheckResponse)
            .where(WellnessCheckResponse.response_id == r.response_id, WellnessCheckResponse.status == PENDING)
            .values(status=new_status)
            .returning(WellnessCheckResponse.response_id)
        ).scalar()
        if won is not None and new_status == ESCALATED:
            res = db.execute(
                pg_insert(EscalationEvent)
                .values(dependent_id=w.dependent_id, trigger_type=EVENT, tier="primary", status="open", reference_id=r.response_id)
                .on_conflict_do_nothing()
                .returning(EscalationEvent.event_id)
            ).scalar()
            opened += res is not None
        db.commit()
    return opened
