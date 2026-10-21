"""
Manual vitals (Task 5.3, FR-H1): blood pressure, blood sugar, oxygen saturation and body temperature.

Who: the Dependent (their own), the Primary Guardian, or a Secondary with the `health_records` permission (the same
gate as the Medical Vault, FR-A4). Delete: whoever typed the reading, or the Primary. Fixed units are stored and
returned: mmHg, mg/dL, %, degrees Celsius (a Dependent may type mmol/L or Fahrenheit; it is converted).
The numbers are only checked for being possible, never judged: the app does not say "high" or "low" (no medical advice).
"""

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, User, VitalReading
from app.models.medical import MANUAL_METRICS, VITAL_METRICS
from app.schemas.vitals import LatestVitals, VitalIn, VitalList, VitalOut
from app.services import linkage_service, records_pdf, records_service

UNITS = {"blood_pressure": "mmHg", "blood_sugar": "mg/dL", "spo2": "%", "temperature": "C", "heart_rate": "bpm"}
MGDL_PER_MMOL = 18.016


def _bad(msg: str, field: str | None = None) -> AppError:
    return AppError(422, "VITAL_OUT_OF_RANGE", msg, {"field": field} if field else None)


def normalise(body: VitalIn) -> tuple[float, float | None]:
    """(value, diastolic) in the stored units, after checking they are possible numbers."""
    m, v, d = body.metric_type, body.value, body.diastolic
    unit = (body.unit or "").strip()
    if m == "blood_pressure":
        if unit and unit.lower() != "mmhg":
            raise AppError(422, "VALIDATION_ERROR", "Blood pressure is in mmHg.")
        if d is None:
            raise AppError(422, "VALIDATION_ERROR", "Send both numbers: value (top) and diastolic (bottom).")
        if not 50 <= v <= 300:
            raise _bad("The top number must be between 50 and 300 mmHg.", "value")
        if not 30 <= d <= 200:
            raise _bad("The bottom number must be between 30 and 200 mmHg.", "diastolic")
        if v <= d:
            raise _bad("The top number must be higher than the bottom number.", "value")
        return round(v, 1), round(d, 1)
    if d is not None:
        raise AppError(422, "VALIDATION_ERROR", "diastolic is only for blood pressure.")
    if m == "blood_sugar":
        if unit.lower() in ("", "mg/dl"):
            pass
        elif unit.lower() == "mmol/l":
            v = v * MGDL_PER_MMOL
        else:
            raise AppError(422, "VALIDATION_ERROR", "Blood sugar unit must be mg/dL or mmol/L.")
        if not 10 <= v <= 1000:
            raise _bad("Blood sugar must be between 10 and 1000 mg/dL.", "value")
        return round(v, 1), None
    if body.context is not None:
        raise AppError(422, "VALIDATION_ERROR", "context is only for blood sugar.")
    if m == "spo2":
        if unit and unit != "%":
            raise AppError(422, "VALIDATION_ERROR", "Oxygen saturation is in percent.")
        if not 50 <= v <= 100:
            raise _bad("Oxygen saturation must be between 50 and 100 percent.", "value")
        return round(v, 1), None
    # temperature
    if unit.upper() in ("", "C"):
        pass
    elif unit.upper() == "F":
        v = (v - 32) * 5 / 9
    else:
        raise AppError(422, "VALIDATION_ERROR", "Temperature unit must be C or F.")
    if not 30 <= v <= 45:
        raise _bad("Body temperature must be between 30 and 45 degrees Celsius (86 to 113 F).", "value")
    return round(v, 1), None


def _out(r: VitalReading, names: dict, user: User, primary: bool, *, already: bool = False) -> VitalOut:
    return VitalOut(
        reading_id=r.reading_id, dependent_id=r.dependent_id, metric_type=r.metric_type, value=r.value, diastolic=r.diastolic,
        unit=UNITS[r.metric_type], context=r.context, note=r.note, source=r.source, recorded_at=r.recorded_at, created_at=r.created_at,
        recorded_by=r.recorded_by, recorded_by_name=names.get(r.recorded_by) if r.recorded_by else None,
        can_delete=primary or (r.recorded_by is not None and r.recorded_by == user.user_id), already_saved=already,
    )


def _outs(db: Session, rows: list[VitalReading], user: User, dependent_id: uuid.UUID, *, already: bool = False) -> list[VitalOut]:
    primary = records_service._is_primary(db, user, dependent_id)
    names = records_service._name_map(db, {r.recorded_by for r in rows if r.recorded_by})
    return [_out(r, names, user, primary, already=already) for r in rows]


def create(db: Session, user: User, dependent_id: uuid.UUID, body: VitalIn) -> VitalOut:
    s = get_settings()
    records_service.authorize(db, user, dependent_id)
    value, diastolic = normalise(body)
    note = records_service._text(body.note, "The note") or None
    now = datetime.now(timezone.utc)
    if body.recorded_at is not None:
        if body.recorded_at.tzinfo is None:
            raise AppError(422, "VALIDATION_ERROR", "recorded_at needs a time zone, for example 2026-10-20T09:30:00+05:00.")
        if body.recorded_at > now + timedelta(minutes=5):
            raise AppError(422, "INVALID_DATE", "The time of the reading cannot be in the future.")
        if body.recorded_at < now - timedelta(days=s.VITALS_MAX_BACKDATE_DAYS):
            raise AppError(422, "INVALID_DATE", f"The reading cannot be older than {s.VITALS_MAX_BACKDATE_DAYS} days.")
    at = body.recorded_at or now

    def same(old: VitalReading) -> bool:
        return (old.dependent_id == dependent_id and old.metric_type == body.metric_type and old.value == value
                and old.diastolic == diastolic and old.context == body.context and old.note == note
                and (body.recorded_at is None or old.recorded_at == body.recorded_at))

    def repeat() -> VitalOut | None:
        if body.client_id is None:
            return None
        old = db.scalar(select(VitalReading).where(VitalReading.recorded_by == user.user_id, VitalReading.client_id == body.client_id))
        if old is None:
            return None
        if not same(old):
            raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different reading.")
        return _outs(db, [old], user, dependent_id, already=True)[0]

    if (again := repeat()) is not None:
        return again
    try:
        linkage_service._lock_dependent(db, dependent_id)  # one at a time per Dependent: the cap cannot be beaten
        if (again := repeat()) is not None:
            db.rollback()
            return again
        count = db.scalar(select(func.count()).select_from(VitalReading).where(VitalReading.dependent_id == dependent_id, VitalReading.source == "manual"))
        if count >= s.VITALS_MAX_PER_DEPENDENT:
            raise AppError(409, "VITALS_LIMIT", f"{s.VITALS_MAX_PER_DEPENDENT} readings are already saved. Delete old ones first.")
        r = VitalReading(
            dependent_id=dependent_id, metric_type=body.metric_type, value=value, diastolic=diastolic, context=body.context,
            note=note, recorded_by=user.user_id, recorded_at=at, source="manual", client_id=body.client_id,
        )
        db.add(r)
        db.flush()
        db.add(AuditLog(actor_id=user.user_id, action="vital_added", target_type="vital_reading", target_id=r.reading_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different reading.")
    except BaseException:
        db.rollback()
        raise
    db.refresh(r)
    return _outs(db, [r], user, dependent_id)[0]


def _bounds(from_: datetime | None, to: datetime | None) -> list:
    out = []
    if from_ is not None:
        if from_.tzinfo is None:
            raise AppError(422, "VALIDATION_ERROR", "`from` needs a time zone.")
        out.append(VitalReading.recorded_at >= from_)
    if to is not None:
        if to.tzinfo is None:
            raise AppError(422, "VALIDATION_ERROR", "`to` needs a time zone.")
        out.append(VitalReading.recorded_at <= to)
    if from_ is not None and to is not None and from_ > to:
        raise AppError(422, "VALIDATION_ERROR", "`from` is after `to`.")
    return out


def list_vitals(
    db: Session, user: User, dependent_id: uuid.UUID, *, metric: str | None, from_: datetime | None, to: datetime | None, limit: int, offset: int
) -> VitalList:
    records_service.authorize(db, user, dependent_id)
    if metric is not None and metric not in VITAL_METRICS:
        raise AppError(422, "VALIDATION_ERROR", "Unknown metric.", {"allowed": list(VITAL_METRICS)})
    where = [VitalReading.dependent_id == dependent_id, *_bounds(from_, to)]
    if metric is not None:
        where.append(VitalReading.metric_type == metric)
    total = db.scalar(select(func.count()).select_from(VitalReading).where(*where))
    rows = list(db.scalars(
        select(VitalReading).where(*where)
        .order_by(VitalReading.recorded_at.desc(), VitalReading.created_at.desc(), VitalReading.reading_id.desc())
        .limit(limit).offset(offset)
    ))
    return VitalList(items=_outs(db, rows, user, dependent_id), total=total, limit=limit, offset=offset)


def latest(db: Session, user: User, dependent_id: uuid.UUID) -> LatestVitals:
    records_service.authorize(db, user, dependent_id)
    rows = list(db.scalars(
        select(VitalReading).where(VitalReading.dependent_id == dependent_id)
        .distinct(VitalReading.metric_type)
        .order_by(VitalReading.metric_type, VitalReading.recorded_at.desc(), VitalReading.created_at.desc(), VitalReading.reading_id.desc())
    ))
    outs = {o.metric_type: o for o in _outs(db, rows, user, dependent_id)}
    return LatestVitals(dependent_id=dependent_id, latest={m: outs.get(m) for m in VITAL_METRICS})


def _get(db: Session, user: User, dependent_id: uuid.UUID, reading_id: uuid.UUID, *, lock: bool = False) -> VitalReading:
    records_service.authorize(db, user, dependent_id)
    q = select(VitalReading).where(VitalReading.reading_id == reading_id, VitalReading.dependent_id == dependent_id)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise AppError(404, "VITAL_NOT_FOUND", "Reading not found.")
    return r


def get_one(db: Session, user: User, dependent_id: uuid.UUID, reading_id: uuid.UUID) -> VitalOut:
    return _outs(db, [_get(db, user, dependent_id, reading_id)], user, dependent_id)[0]


def delete(db: Session, user: User, dependent_id: uuid.UUID, reading_id: uuid.UUID) -> None:
    r = _get(db, user, dependent_id, reading_id, lock=True)
    if r.recorded_by != user.user_id and not records_service._is_primary(db, user, dependent_id):
        raise AppError(403, "VITAL_MODIFY_DENIED", "Only the person who typed this reading, or the Primary Guardian, can delete it.")
    db.delete(r)
    db.add(AuditLog(actor_id=user.user_id, action="vital_deleted", target_type="vital_reading", target_id=reading_id))
    db.commit()


# ------------------------------------------------------------------ export (FR-H1 "separate PDF, or combined")

def period_bounds(year: int | None, month: int | None) -> list:
    """The period in the clinic's local time (APPOINTMENT_TIMEZONE), so "March" means March where the family lives."""
    if year is None:
        return []
    tz = ZoneInfo(get_settings().APPOINTMENT_TIMEZONE)
    if month is None:
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    else:
        start, end = date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)
    return [
        VitalReading.recorded_at >= datetime(start.year, start.month, start.day, tzinfo=tz),
        VitalReading.recorded_at < datetime(end.year, end.month, end.day, tzinfo=tz),
    ]


def band_summary(db: Session, dependent_id: uuid.UUID, year: int | None, month: int | None) -> list[dict]:
    """Band readings are one every minute or so, far too many to list: the PDF shows one line per day and metric (Task 5.4)."""
    tz = get_settings().APPOINTMENT_TIMEZONE
    day = func.date(func.timezone(tz, VitalReading.recorded_at)).label("day")
    q = (
        select(day, VitalReading.metric_type, func.count(), func.avg(VitalReading.value), func.min(VitalReading.value), func.max(VitalReading.value))
        .where(VitalReading.dependent_id == dependent_id, VitalReading.source == "wearable", *period_bounds(year, month))
        .group_by(day, VitalReading.metric_type).order_by(day.desc(), VitalReading.metric_type).limit(1100)
    )
    return [{"day": d, "metric": m, "n": n, "avg": float(a), "min": float(lo), "max": float(hi)} for d, m, n, a, lo, hi in db.execute(q)]


def export_rows(db: Session, dependent_id: uuid.UUID, year: int | None, month: int | None) -> tuple[list[dict], int, list[dict]]:
    """(newest typed readings as plain rows for the PDF, how many matched, one summary line per day for the band's readings)."""
    s = get_settings()
    where = [VitalReading.dependent_id == dependent_id, VitalReading.source == "manual", *period_bounds(year, month)]
    total = db.scalar(select(func.count()).select_from(VitalReading).where(*where))
    rows = list(db.scalars(
        select(VitalReading).where(*where)
        .order_by(VitalReading.recorded_at.desc(), VitalReading.created_at.desc(), VitalReading.reading_id.desc())
        .limit(s.EXPORT_MAX_VITALS)
    ))
    names = records_service._name_map(db, {r.recorded_by for r in rows if r.recorded_by})
    return [
        {
            "at": r.recorded_at, "metric": r.metric_type, "value": r.value, "diastolic": r.diastolic, "context": r.context,
            "note": r.note, "by": names.get(r.recorded_by) or "A Guardian",
        }
        for r in rows
    ], total, band_summary(db, dependent_id, year, month)


def export_pdf(db: Session, user: User, dependent_id: uuid.UUID, scope: str, year: int | None, month: int | None) -> tuple[bytes, str]:
    records_service.authorize(db, user, dependent_id)
    rows, total, band = export_rows(db, dependent_id, year, month)
    names = records_service._name_map(db, {dependent_id})
    pdf = records_pdf.build_vitals(person_name=names.get(dependent_id) or "Dependent", scope=scope, year=year, month=month, rows=rows, total_matching=total, band=band)
    db.add(AuditLog(actor_id=user.user_id, action="vitals_exported", target_type="dependent", target_id=dependent_id))
    db.commit()
    return pdf, records_pdf.file_stem(scope, year, month).replace("records", "vitals") + ".pdf"
