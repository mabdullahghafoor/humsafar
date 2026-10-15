"""
Device health: battery and connectivity (Task 2.3, FR-L1 / FR-L2).

Where the data comes from: the Dependent's phone already sends a location fix every 10 to 180 seconds
(Task 2.1) and each fix may carry `battery_level`. That is the heartbeat, so no separate endpoint is needed.

  Low battery (FR-L1)   a fix with battery <= 15% opens ONE `low_battery` event; it closes when a fix shows
                        more than 20% (charging). 16-20% changes nothing, so it cannot flap.
  Offline (FR-L2)       if the newest fix is older than 10 minutes, a background job opens ONE
                        `device_offline` event; any new fix closes it. Distinct from low battery.
  Last known location   always the newest fix. While the battery is low the server asks the phone to check in at
                        least every 60 s, so the last position before a shutdown is as fresh as possible.

Only the newest fix decides (a late buffered upload cannot flip anything). Events are rows in
`escalation_events`, exactly like geofence breaches. Delivering the notification to Guardians is Task 3.1.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DependentProfile, EscalationEvent, GuardianDependentLink, LocationLog
from app.schemas.device_health import DeviceHealthOut, Thresholds
from app.schemas.location import LocationPoint
from app.services import linkage_service

LOW_BATTERY = "low_battery"
OFFLINE = "device_offline"
OPEN, RESOLVED = "open", "resolved"


def _open_event(db: Session, dependent_id: uuid.UUID, kind: str, lock: bool = False) -> EscalationEvent | None:
    q = select(EscalationEvent).where(
        EscalationEvent.dependent_id == dependent_id, EscalationEvent.trigger_type == kind, EscalationEvent.status == OPEN
    )
    if lock:
        q = q.with_for_update()
    return db.scalars(q.order_by(EscalationEvent.created_at.desc())).first()


def _set_state(db: Session, dependent_id: uuid.UUID, kind: str, want_open: bool) -> bool:
    """
    Make the open/closed state of one event kind match `want_open`. Returns True only when a NEW event was opened.
    Locks the Dependent row before changing anything, so simultaneous requests or sweeps cannot open two.
    Does not commit.
    """
    if (_open_event(db, dependent_id, kind) is not None) == want_open:
        return False  # already right: the common case, no lock
    linkage_service._lock_dependent(db, dependent_id)
    existing = _open_event(db, dependent_id, kind, lock=True)
    if want_open:
        if existing is not None:
            return False
        db.add(EscalationEvent(dependent_id=dependent_id, trigger_type=kind, tier="primary", status=OPEN))
        db.flush()
        return True
    if existing is not None:
        existing.status = RESOLVED
        existing.resolved_at = datetime.now(timezone.utc)
        db.flush()
    return False


def _latest_log(db: Session, dependent_id: uuid.UUID) -> LocationLog | None:
    return db.scalar(
        select(LocationLog).where(LocationLog.dependent_id == dependent_id).order_by(LocationLog.recorded_at.desc()).limit(1)
    )


# ------------------------------------------------------------ called by location ingest

def is_low(battery_level: int | None) -> bool:
    return battery_level is not None and battery_level <= get_settings().DEVICE_LOW_BATTERY_PCT


def on_new_fix(db: Session, dependent_id: uuid.UUID, log: LocationLog) -> tuple[bool, bool]:
    """
    Called after a fix is stored. Returns (low_battery_open, low_battery_started).
    Any fix closes an open offline event (the phone is clearly back). A fix that is not the newest does nothing.
    """
    newest = _latest_log(db, dependent_id)
    if newest is not None and newest.log_id != log.log_id and newest.recorded_at > log.recorded_at:
        return _open_event(db, dependent_id, LOW_BATTERY) is not None, False

    s = get_settings()
    _set_state(db, dependent_id, OFFLINE, want_open=False)
    started = False
    level = log.battery_level
    if level is not None:
        if level <= s.DEVICE_LOW_BATTERY_PCT:
            started = _set_state(db, dependent_id, LOW_BATTERY, want_open=True)
        elif level > s.DEVICE_BATTERY_RECOVER_PCT:
            _set_state(db, dependent_id, LOW_BATTERY, want_open=False)
    db.commit()
    return _open_event(db, dependent_id, LOW_BATTERY) is not None, started


# ------------------------------------------------------------ background job

def sweep_offline(db: Session, now: datetime | None = None) -> int:
    """
    FR-L2: open a `device_offline` event for every active Dependent whose newest fix is older than the
    threshold and who has none open yet. Returns how many were opened. Safe to run from several processes.
    Dependents that have never sent a fix are skipped: nothing is known about their phone yet.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=get_settings().DEVICE_OFFLINE_AFTER_S)
    last_seen = (
        select(LocationLog.dependent_id, func.max(LocationLog.recorded_at).label("seen"))
        .group_by(LocationLog.dependent_id)
        .subquery()
    )
    has_primary = (
        select(GuardianDependentLink.dependent_id)
        .where(GuardianDependentLink.role == "primary", GuardianDependentLink.status == linkage_service.ACTIVE)
        .subquery()
    )
    ids = db.scalars(
        select(last_seen.c.dependent_id)
        .where(last_seen.c.seen < cutoff, last_seen.c.dependent_id.in_(select(has_primary.c.dependent_id)))
    ).all()
    opened = 0
    for dep_id in ids:
        # re-check inside the lock: a fix may have arrived since the query
        linkage_service._lock_dependent(db, dep_id)
        newest = _latest_log(db, dep_id)
        if newest is None or newest.recorded_at >= cutoff:
            db.rollback()
            continue
        if _set_state(db, dep_id, OFFLINE, want_open=True):
            opened += 1
        db.commit()
    return opened


# ------------------------------------------------------------ read

def health(db: Session, dependent_id: uuid.UUID, now: datetime | None = None) -> DeviceHealthOut:
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    newest = _latest_log(db, dependent_id)
    with_battery = db.scalar(
        select(LocationLog)
        .where(LocationLog.dependent_id == dependent_id, LocationLog.battery_level.is_not(None))
        .order_by(LocationLog.recorded_at.desc())
        .limit(1)
    )
    low = _open_event(db, dependent_id, LOW_BATTERY)
    off = _open_event(db, dependent_id, OFFLINE)

    if newest is None:
        conn, age, cause = "unknown", None, None
    else:
        age = max(0, int((now - newest.recorded_at).total_seconds()))
        conn = "offline" if age > s.DEVICE_OFFLINE_AFTER_S else "online"
        cause = None
        if conn == "offline":
            depleted = with_battery is not None and with_battery.battery_level <= s.DEVICE_BATTERY_DEPLETED_PCT
            cause = "battery_depleted" if depleted else "connectivity_or_unknown"
    return DeviceHealthOut(
        dependent_id=dependent_id,
        battery_level=with_battery.battery_level if with_battery else None,
        battery_reported_at=with_battery.recorded_at if with_battery else None,
        low_battery=low is not None,
        low_battery_since=low.created_at if low else None,
        connectivity=conn,
        last_seen_at=newest.recorded_at if newest else None,
        seconds_since_seen=age,
        offline_alert_open=off is not None,
        offline_alert_since=off.created_at if off else None,
        probable_cause=cause,
        last_known_location=(
            LocationPoint(lat=newest.lat, lng=newest.lng, recorded_at=newest.recorded_at, battery_level=newest.battery_level)
            if newest
            else None
        ),
        thresholds=Thresholds(
            low_battery_pct=s.DEVICE_LOW_BATTERY_PCT,
            battery_recover_pct=s.DEVICE_BATTERY_RECOVER_PCT,
            offline_after_s=s.DEVICE_OFFLINE_AFTER_S,
        ),
    )
