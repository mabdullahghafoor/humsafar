"""
Wearable band (Task 5.4, FR-H2), built and tested against MOCK data first; the real device is Task 5.5.

How it fits (clarifications 88, 89, 113 to 118):
  Band --Bluetooth--> Dependent's phone --POST /dependents/{id}/wearable/sync--> server.
  The band is paired once per Dependent (one band each). The phone sends batches of readings
  (heart_rate, and spo2 / temperature when the band has those sensors). Readings land in `vital_readings`
  with source = 'wearable', so the vitals list, latest values and PDF already show them.

  Safe retry   a sample is identified by (Dependent, metric, measured time): sending a batch twice stores it once.
  Bad values   a reading that is impossible, too old or in the future is skipped and reported; the rest are kept
               (one broken sensor reading must not block every later sync).
  "No data"    FR-H2 "handle disconnection gracefully" + clarification 88: if a paired band has produced no new
               measurement for BAND_NO_DATA_AFTER_S (30 min), a background job opens ONE `band_no_data` event and the
               Primary (and Secondaries with health_records) get a STANDARD notice. A newer measurement closes it.
               It is not raised while the phone itself is offline (`device_offline` is already open: the phone cannot
               send anything, and that alert is the real cause).
  Nothing blocks: every other feature works with no band paired or a silent band.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, GuardianDependentLink, User, VitalReading, WearableDevice
from app.schemas.vitals import VitalOut
from app.schemas.wearable import BandOut, BandPairIn, BandReadingIn, BandStatus, MockIn, Rejected, SyncIn, SyncOut
from app.services import device_health_service, linkage_service, records_service, vitals_service

NO_DATA = "band_no_data"
RANGES = {"heart_rate": (20.0, 250.0), "spo2": (50.0, 100.0), "temperature": (30.0, 45.0)}
FUTURE_SLACK = timedelta(minutes=5)

_last_purge: datetime | None = None


def _out(d: WearableDevice) -> BandOut:
    return BandOut(device_id=d.device_id, dependent_id=d.dependent_id, ble_address=d.ble_address, name=d.name, paired_at=d.paired_at, last_sync_at=d.last_sync_at)


def _band(db: Session, dependent_id: uuid.UUID) -> WearableDevice | None:
    return db.scalar(select(WearableDevice).where(WearableDevice.dependent_id == dependent_id))


def _require_owner_or_primary(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    """The Dependent (their own phone) or the Primary Guardian sets the band up."""
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return
    if not records_service._is_primary(db, user, dependent_id):
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Dependent or the Primary Guardian can do this.")


def _audit(db: Session, user: User, action: str, dependent_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=user.user_id, action=action, target_type="dependent", target_id=dependent_id))


# ------------------------------------------------------------ pair / unpair

def pair(db: Session, user: User, dependent_id: uuid.UUID, body: BandPairIn) -> tuple[BandOut, bool]:
    """(band, created). Pairing the same address again is fine (200); another address while one is paired is 409."""
    _require_owner_or_primary(db, user, dependent_id)
    name = records_service._text(body.name, "The name") or None
    linkage_service._lock_dependent(db, dependent_id)
    old = _band(db, dependent_id)
    if old is not None:
        db.rollback()
        if old.ble_address == body.ble_address:
            return _out(old), False
        raise AppError(409, "BAND_ALREADY_PAIRED", "A band is already paired. Unpair it first.", {"ble_address": old.ble_address})
    d = WearableDevice(dependent_id=dependent_id, ble_address=body.ble_address, name=name)
    db.add(d)
    db.flush()
    _audit(db, user, "wearable_paired", dependent_id)
    db.commit()
    db.refresh(d)
    return _out(d), True


def unpair(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    """Safe to repeat. The readings already stored stay; an open "no data" notice is closed."""
    _require_owner_or_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    d = _band(db, dependent_id)
    if d is None:
        db.rollback()
        return
    db.delete(d)
    device_health_service._set_state(db, dependent_id, NO_DATA, want_open=False)
    _audit(db, user, "wearable_unpaired", dependent_id)
    db.commit()


# ------------------------------------------------------------ storing readings

def _check(r: BandReadingIn, now: datetime, oldest: datetime) -> str | None:
    if r.recorded_at.tzinfo is None:
        return "recorded_at needs a time zone."
    if r.recorded_at > now + FUTURE_SLACK:
        return "The time is in the future."
    if r.recorded_at < oldest:
        return f"The reading is older than {get_settings().WEARABLE_BACKFILL_DAYS} days."
    lo, hi = RANGES[r.metric_type]
    if not lo <= r.value <= hi:
        return f"{r.metric_type} must be between {lo:g} and {hi:g}."
    return None


def _store(db: Session, dependent_id: uuid.UUID, band: WearableDevice, items: list[tuple[int, BandReadingIn]], total: int, *, note: str | None = None) -> SyncOut:
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(days=get_settings().WEARABLE_BACKFILL_DAYS)
    rejected: list[Rejected] = []
    good: dict[tuple[str, datetime], dict] = {}
    for idx, r in items:
        why = _check(r, now, oldest)
        if why:
            rejected.append(Rejected(index=idx, reason=why))
            continue
        key = (r.metric_type, r.recorded_at)
        good.setdefault(key, {
            "dependent_id": dependent_id, "metric_type": r.metric_type, "value": round(r.value, 1), "recorded_at": r.recorded_at,
            "source": "wearable", "recorded_by": None, "note": note,
        })
    stored = 0
    if good:
        stmt = (
            pg_insert(VitalReading).values(list(good.values()))
            .on_conflict_do_nothing(index_elements=["dependent_id", "metric_type", "recorded_at"], index_where=text("source = 'wearable'"))
            .returning(VitalReading.reading_id)
        )
        stored = len(db.execute(stmt).all())
        newest = min(max(k[1] for k in good), now)
        db.execute(
            update(WearableDevice).where(WearableDevice.device_id == band.device_id)
            .values(last_sync_at=func.greatest(func.coalesce(WearableDevice.last_sync_at, newest), newest))
        )
    db.commit()
    db.refresh(band)
    _close_if_fresh(db, dependent_id, band)
    duplicates = len(items) - len(rejected) - stored  # already stored, or repeated inside this batch
    return SyncOut(received=total, stored=stored, duplicates=duplicates, rejected=sorted(rejected, key=lambda x: x.index), last_sync_at=band.last_sync_at)


def _close_if_fresh(db: Session, dependent_id: uuid.UUID, band: WearableDevice) -> None:
    s = get_settings()
    if band.last_sync_at is not None and datetime.now(timezone.utc) - band.last_sync_at <= timedelta(seconds=s.BAND_NO_DATA_AFTER_S):
        device_health_service._set_state(db, dependent_id, NO_DATA, want_open=False)
        db.commit()


def sync(db: Session, user: User, dependent_id: uuid.UUID, body: SyncIn) -> SyncOut:
    """The Dependent's own phone sends what the band measured."""
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "Only the Dependent's own phone can send band readings.")
    if len(body.readings) > get_settings().WEARABLE_MAX_BATCH:
        raise AppError(422, "VALIDATION_ERROR", f"Send at most {get_settings().WEARABLE_MAX_BATCH} readings at a time.")
    band = _band(db, dependent_id)
    if band is None:
        raise AppError(409, "NO_BAND", "No band is paired. Pair it first.")
    return _store(db, dependent_id, band, list(enumerate(body.readings)), len(body.readings))


def mock(db: Session, user: User, dependent_id: uuid.UUID, body: MockIn) -> SyncOut:
    """Demo data: fake heart-rate readings that end now, for the screens and the demo while there is no real band."""
    if not get_settings().WEARABLE_MOCK_ENABLED:
        raise AppError(404, "NOT_FOUND", "Not found.")
    _require_owner_or_primary(db, user, dependent_id)
    band = _band(db, dependent_id)
    if band is None:
        raise AppError(409, "NO_BAND", "No band is paired. Pair it first.")
    end = datetime.now(timezone.utc).replace(microsecond=0)
    bpm, items = random.randint(66, 82), []
    for i in range(body.count):
        bpm = max(52, min(110, bpm + random.randint(-3, 3)))
        items.append((i, BandReadingIn(metric_type="heart_rate", value=bpm, recorded_at=end - timedelta(seconds=i * body.interval_s))))
    return _store(db, dependent_id, band, items, len(items), note="mock band data")


# ------------------------------------------------------------ status

def status(db: Session, user: User, dependent_id: uuid.UUID) -> BandStatus:
    records_service.authorize(db, user, dependent_id)
    s = get_settings()
    now = datetime.now(timezone.utc)
    band = _band(db, dependent_id)
    ev = device_health_service._open_event(db, dependent_id, NO_DATA)
    hr = db.scalar(
        select(VitalReading).where(VitalReading.dependent_id == dependent_id, VitalReading.metric_type == "heart_rate")
        .order_by(VitalReading.recorded_at.desc(), VitalReading.created_at.desc(), VitalReading.reading_id.desc()).limit(1)
    )
    latest: VitalOut | None = vitals_service._outs(db, [hr], user, dependent_id)[0] if hr else None
    if band is None:
        st, age = "not_paired", None
    else:
        ref = band.last_sync_at or band.paired_at
        stale = now - ref > timedelta(seconds=s.BAND_NO_DATA_AFTER_S)
        st = "no_data" if stale else ("receiving" if band.last_sync_at else "waiting_for_first_data")
        age = max(0, int((now - band.last_sync_at).total_seconds())) if band.last_sync_at else None
    return BandStatus(
        dependent_id=dependent_id, status=st, device=_out(band) if band else None, last_data_at=band.last_sync_at if band else None,
        seconds_since_data=age, no_data_alert_open=ev is not None, no_data_alert_since=ev.created_at if ev else None,
        no_data_after_s=s.BAND_NO_DATA_AFTER_S, latest_heart_rate=latest,
    )


# ------------------------------------------------------------ background job

def sweep_no_data(db: Session, now: datetime | None = None) -> int:
    """
    Open a `band_no_data` event for every paired band that has produced nothing for BAND_NO_DATA_AFTER_S
    (counted from pairing if it never sent anything). Skipped while the phone is offline. Also deletes band
    readings older than WEARABLE_RETENTION_DAYS (about once an hour). Returns how many events were opened.
    """
    global _last_purge
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=s.BAND_NO_DATA_AFTER_S)
    has_primary = (
        select(GuardianDependentLink.dependent_id)
        .where(GuardianDependentLink.role == "primary", GuardianDependentLink.status == linkage_service.ACTIVE)
        .subquery()
    )
    ids = db.scalars(
        select(WearableDevice.dependent_id).where(
            func.coalesce(WearableDevice.last_sync_at, WearableDevice.paired_at) < cutoff,
            WearableDevice.dependent_id.in_(select(has_primary.c.dependent_id)),
        )
    ).all()
    opened = 0
    for dep_id in ids:
        linkage_service._lock_dependent(db, dep_id)
        band = db.scalar(select(WearableDevice).where(WearableDevice.dependent_id == dep_id).with_for_update())  # re-check inside the lock
        stale = band is not None and (band.last_sync_at or band.paired_at) < cutoff
        phone_offline = device_health_service._open_event(db, dep_id, device_health_service.OFFLINE) is not None
        if stale and not phone_offline and device_health_service._set_state(db, dep_id, NO_DATA, want_open=True):
            opened += 1
        db.commit()
    if _last_purge is None or now - _last_purge >= timedelta(hours=1):
        _last_purge = now
        db.execute(delete(VitalReading).where(VitalReading.source == "wearable", VitalReading.recorded_at < now - timedelta(days=s.WEARABLE_RETENTION_DAYS)))
        db.commit()
    return opened
