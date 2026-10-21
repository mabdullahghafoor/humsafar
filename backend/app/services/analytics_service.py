"""
Adherence and vitals analytics (Task 7.1, FR-Q1).

Read only. Everything is computed from data that already exists: `medication_confirmations` (3.2/3.3) for adherence,
`vital_readings` (5.3 manual, 5.4 band) for vitals. Nothing new is stored.

Who     Guardians only (the SRS says "to the Guardian"). Adherence needs `medication_management`, vitals need
        `health_records`; the Primary has both. A Dependent is refused (clarification 164).
Days    Calendar days in MEDICATION_TIMEZONE (default Asia/Karachi); `days` = 1..90 counting today, so days=7
        is today and the 6 days before it.
Adherence   Only decided doses count: taken, or missed. A dose still waiting is shown as `waiting`, not in the rate.
            A removed schedule keeps its history (3.2), so its doses still count.
Vitals      Per metric: count, min, max, average, newest reading, one entry per day with data, and a trend that
            compares the second half of the period to the first half. The trend only describes the numbers
            ("rising", "falling", "steady"); it never says good or bad (no medical advice, as in 5.3).
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import MedicationConfirmation, MedicationSchedule, User, VitalReading
from app.models.medical import VITAL_METRICS
from app.schemas.analytics import (
    AdherenceDay,
    AdherenceMedicine,
    AdherencePeriod,
    AdherenceReport,
    AnalyticsOverview,
    VitalDay,
    VitalLatest,
    VitalMetricReport,
    VitalsReport,
)
from app.services import medication_service, permission_service
from app.services.vitals_service import UNITS

MIN_DAYS, MAX_DAYS = 1, 90
STEADY_PERCENT = 3.0  # vitals: a change smaller than this (percent of the first half) is "steady"
ADHERENCE_STEADY_POINTS = 5.0  # adherence: a change smaller than this many points is "steady"
MIN_PER_HALF = 1  # readings needed in each half before a trend is given


# ------------------------------------------------------------------ helpers

def _rate(taken: int, missed: int) -> float | None:
    return round(taken * 100 / (taken + missed), 1) if taken + missed else None


def _window(days: int) -> tuple[date, date, datetime]:
    """(first local day, today, UTC moment the first day starts)."""
    today = datetime.now(timezone.utc).astimezone(medication_service.tz()).date()
    first = today - timedelta(days=days - 1)
    return first, today, medication_service.occurrence(first, time(0, 0))


def _guardian_only(user: User) -> None:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")


def _check_days(days: int) -> None:
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise AppError(422, "VALIDATION_ERROR", f"days must be between {MIN_DAYS} and {MAX_DAYS}.")


# ------------------------------------------------------------------ adherence

def _doses(db: Session, dependent_id: uuid.UUID, start: datetime, end: datetime):
    return db.execute(
        select(MedicationConfirmation.scheduled_for, MedicationConfirmation.status, MedicationSchedule.drug_name, MedicationSchedule.dosage)
        .join(MedicationSchedule, MedicationSchedule.schedule_id == MedicationConfirmation.schedule_id)
        .where(
            MedicationSchedule.dependent_id == dependent_id,
            MedicationConfirmation.scheduled_for >= start,
            MedicationConfirmation.scheduled_for < end,
        )
    ).all()


def adherence(db: Session, user: User, dependent_id: uuid.UUID, days: int = 30) -> AdherenceReport:
    _check_days(days)
    permission_service.check_module_access(db, user, dependent_id, medication_service.MODULE)
    return _adherence(db, dependent_id, days)


def _adherence(db: Session, dependent_id: uuid.UUID, days: int) -> AdherenceReport:
    first, today, start = _window(days)
    now = datetime.now(timezone.utc)
    prev_start = medication_service.occurrence(first - timedelta(days=days), time(0, 0))
    local = medication_service.tz()

    per_day = {first + timedelta(days=i): [0, 0] for i in range(days)}  # day -> [taken, missed]
    per_med: dict[tuple[str, str], list[int]] = {}
    waiting = 0
    for at, status, drug, dosage in _doses(db, dependent_id, start, now):
        if status == medication_service.PENDING:
            waiting += 1
            continue
        i = 0 if status == medication_service.TAKEN else 1
        per_day[at.astimezone(local).date()][i] += 1
        per_med.setdefault((drug, dosage), [0, 0])[i] += 1

    taken = sum(v[0] for v in per_day.values())
    missed = sum(v[1] for v in per_day.values())
    rate = _rate(taken, missed)

    p_taken = p_missed = 0
    for _at, status, _d, _g in _doses(db, dependent_id, prev_start, start):
        if status == medication_service.TAKEN:
            p_taken += 1
        elif status == medication_service.MISSED:
            p_missed += 1
    p_rate = _rate(p_taken, p_missed)

    change_points = round(rate - p_rate, 1) if rate is not None and p_rate is not None else None
    if change_points is None:
        change = "not_enough_data"
    elif change_points >= ADHERENCE_STEADY_POINTS:
        change = "improving"
    elif change_points <= -ADHERENCE_STEADY_POINTS:
        change = "declining"
    else:
        change = "steady"

    streak = 0
    for d in sorted(per_day, reverse=True):
        t, m = per_day[d]
        if m:
            break
        if t:
            streak += 1

    return AdherenceReport(
        days=days, from_date=first, to_date=today, timezone=str(local),
        taken=taken, missed=missed, waiting=waiting, rate_percent=rate,
        previous=AdherencePeriod(taken=p_taken, missed=p_missed, rate_percent=p_rate),
        change_points=change_points, change=change, perfect_days_in_a_row=streak,
        daily=[AdherenceDay(date=d, taken=v[0], missed=v[1], rate_percent=_rate(*v)) for d, v in sorted(per_day.items())],
        by_medicine=[
            AdherenceMedicine(drug_name=k[0], dosage=k[1], taken=v[0], missed=v[1], rate_percent=_rate(*v))
            for k, v in sorted(per_med.items())
        ],
    )


# ------------------------------------------------------------------ vitals

def vitals(db: Session, user: User, dependent_id: uuid.UUID, days: int = 30, metric: str | None = None) -> VitalsReport:
    _check_days(days)
    if metric is not None and metric not in VITAL_METRICS:
        raise AppError(422, "VALIDATION_ERROR", "metric must be one of: " + ", ".join(VITAL_METRICS))
    from app.services import records_service  # same gate as the vitals themselves (5.3)

    _guardian_only(user)
    records_service.authorize(db, user, dependent_id)
    return _vitals(db, dependent_id, days, metric)


def _trend(daily: list[tuple[date, int, float]], mid: date) -> tuple[str, float | None]:
    """daily = (day, count, average) with data. First half = days before `mid`."""
    first = [(c, a) for d, c, a in daily if d < mid]
    second = [(c, a) for d, c, a in daily if d >= mid]
    n1, n2 = sum(c for c, _ in first), sum(c for c, _ in second)
    if n1 < MIN_PER_HALF or n2 < MIN_PER_HALF:
        return "not_enough_data", None
    a1 = sum(c * a for c, a in first) / n1
    a2 = sum(c * a for c, a in second) / n2
    pct = round((a2 - a1) * 100 / a1, 1) if a1 else None
    if pct is None:
        return "not_enough_data", None
    if abs(pct) < STEADY_PERCENT:
        return "steady", pct
    return ("rising" if pct > 0 else "falling"), pct


def _vitals(db: Session, dependent_id: uuid.UUID, days: int, metric: str | None) -> VitalsReport:
    first, today, start = _window(days)
    local = medication_service.tz()
    day = cast(func.timezone(str(local), VitalReading.recorded_at), Date)
    wearable = func.sum(case((VitalReading.source == "wearable", 1), else_=0))
    q = (
        select(
            VitalReading.metric_type, day.label("d"), func.count(), wearable,
            func.avg(VitalReading.value), func.min(VitalReading.value), func.max(VitalReading.value),
            func.avg(VitalReading.diastolic), func.min(VitalReading.diastolic), func.max(VitalReading.diastolic),
        )
        .where(VitalReading.dependent_id == dependent_id, VitalReading.recorded_at >= start)
        .group_by(VitalReading.metric_type, day)
        .order_by(day)
    )
    by_metric: dict[str, list] = {}
    for row in db.execute(q).all():
        by_metric.setdefault(row[0], []).append(row)

    mid = first + timedelta(days=days // 2) if days > 1 else today
    out = []
    for m in [metric] if metric else VITAL_METRICS:
        rows = by_metric.get(m, [])
        r = lambda x: None if x is None else round(float(x), 1)  # noqa: E731
        daily = [
            VitalDay(date=d, count=c, avg=r(a), min=r(lo), max=r(hi), avg_diastolic=r(da), min_diastolic=r(dlo), max_diastolic=r(dhi))
            for _m, d, c, _w, a, lo, hi, da, dlo, dhi in rows
        ]
        total = sum(x[2] for x in rows)
        wear = sum(int(x[3] or 0) for x in rows)
        latest = None
        if total:
            lr = db.scalar(
                select(VitalReading).where(VitalReading.dependent_id == dependent_id, VitalReading.metric_type == m, VitalReading.recorded_at >= start)
                .order_by(VitalReading.recorded_at.desc()).limit(1)
            )
            latest = VitalLatest(value=lr.value, diastolic=lr.diastolic, recorded_at=lr.recorded_at, source=lr.source)
        trend, pct = _trend([(x[1], x[2], float(x[4])) for x in rows], mid) if total else ("not_enough_data", None)
        diastolics = [(x[2], x[7]) for x in rows if x[7] is not None]
        out.append(VitalMetricReport(
            metric_type=m, unit=UNITS[m], count=total, manual_count=total - wear, wearable_count=wear,
            avg=r(sum(x[2] * float(x[4]) for x in rows) / total) if total else None,
            min=r(min(x[5] for x in rows)) if total else None,
            max=r(max(x[6] for x in rows)) if total else None,
            avg_diastolic=r(sum(c * float(a) for c, a in diastolics) / sum(c for c, _ in diastolics)) if diastolics else None,
            min_diastolic=r(min(x[8] for x in rows if x[8] is not None)) if diastolics else None,
            max_diastolic=r(max(x[9] for x in rows if x[9] is not None)) if diastolics else None,
            latest=latest, trend=trend, change_percent=pct, daily=daily,
        ))
    return VitalsReport(days=days, from_date=first, to_date=today, timezone=str(local), metrics=out)


# ------------------------------------------------------------------ both together

def overview(db: Session, user: User, dependent_id: uuid.UUID, days: int = 30) -> AnalyticsOverview:
    """Both reports in one call. A part the Guardian has no permission for is null; no permission for either is a 403."""
    from app.services import records_service

    _check_days(days)
    _guardian_only(user)
    first_error: AppError | None = None
    adh = vit = None
    try:
        permission_service.check_module_access(db, user, dependent_id, medication_service.MODULE)
        adh = _adherence(db, dependent_id, days)
    except AppError as exc:
        if exc.status_code != 403:
            raise
        first_error = exc
    try:
        records_service.authorize(db, user, dependent_id)
        vit = _vitals(db, dependent_id, days, None)
    except AppError as exc:
        if exc.status_code != 403:
            raise
        first_error = first_error or exc
    if adh is None and vit is None:
        raise first_error
    return AnalyticsOverview(dependent_id=dependent_id, days=days, adherence=adh, vitals=vit)
