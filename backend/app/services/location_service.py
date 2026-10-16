"""
Location ingestion and reading (Task 2.1, FR-C1 / FR-C4).

Adaptive frequency (FR-C1.2): the phone sends a fix, the server decides whether the
Dependent is moving, and replies with how many seconds to wait before the next fix.
The phone only needs to obey `next_update_interval_s` (Talha's Task 2.7).

  moving      speed >= 0.8 m/s, OR moved >= 25 m (and more than the GPS error) since the previous fix
  stationary  not moving
  idle        not moving for the last 10 minutes or more
  first fix   no earlier fix exists, so we treat it as "moving" (short interval) until we know

The movement state is computed, not stored: SDS 9.2 `location_logs` has no such column and
the locked schema is not changed. All thresholds live in Settings so they can be tuned.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.geo import haversine_m  # noqa: F401  (re-exported: tests import it from here)
from app.models import LocationLog, User
from app.services import device_health_service, geofence_service, notification_service
from app.schemas.location import (
    LatestLocationOut,
    LocationAck,
    LocationHistoryOut,
    LocationPoint,
    LocationUpdateRequest,
)

MOVING, STATIONARY, IDLE = "moving", "stationary", "idle"
LOOKBACK_ROWS = 200  # enough to cover the idle window even at the fastest polling rate


def interval_for(state: str) -> int:
    s = get_settings()
    return {
        MOVING: s.LOCATION_INTERVAL_MOVING_S,
        STATIONARY: s.LOCATION_INTERVAL_STATIONARY_S,
        IDLE: s.LOCATION_INTERVAL_IDLE_S,
    }[state]


def _wait_for(state: str, low_battery: bool) -> int:
    """Seconds the phone should wait. While the battery is low, check in at least this often so the
    position saved before a shutdown is as fresh as possible (FR-L1.3)."""
    s = get_settings()
    wait = interval_for(state)
    return min(wait, s.LOCATION_INTERVAL_LOW_BATTERY_S) if low_battery else wait


def classify_movement(
    lat: float,
    lng: float,
    at: datetime,
    previous: list[tuple[float, float, datetime]],
    speed_mps: float | None = None,
    accuracy_m: float | None = None,
) -> str:
    """
    Pure function (easy to test). `previous` = earlier fixes, NEWEST FIRST, all before `at`.
    """
    s = get_settings()
    # Ignore shifts smaller than the GPS error: a bad fix must not look like walking.
    threshold = max(s.LOCATION_MOVE_THRESHOLD_M, accuracy_m or 0.0)

    if speed_mps is not None and speed_mps >= s.LOCATION_MOVING_SPEED_MPS:
        return MOVING
    if not previous:
        return MOVING  # unknown: stay on the short interval until a second fix arrives
    plat, plng, _ = previous[0]
    if haversine_m(lat, lng, plat, plng) >= threshold:
        return MOVING

    # Not moving. How long has the Dependent stayed put? Walk back while fixes are still close.
    oldest_close = previous[0][2]
    for plat, plng, pat in previous:
        if haversine_m(lat, lng, plat, plng) >= threshold:
            break
        oldest_close = pat
    if (at - oldest_close).total_seconds() >= s.LOCATION_IDLE_AFTER_S:
        return IDLE
    return STATIONARY


def ingest(db: Session, user: User, dependent_id: uuid.UUID, req: LocationUpdateRequest) -> LocationAck:
    s = get_settings()
    # Only the Dependent's own phone may report that Dependent's location.
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "You can only send location for your own account.")

    now = datetime.now(timezone.utc)
    at = req.recorded_at.astimezone(timezone.utc) if req.recorded_at else now
    if at > now + timedelta(seconds=s.LOCATION_MAX_FUTURE_S):
        raise AppError(422, "TIMESTAMP_IN_FUTURE", "recorded_at is ahead of the server clock.")
    if at < now - timedelta(seconds=s.LOCATION_MAX_AGE_S):
        raise AppError(422, "TIMESTAMP_TOO_OLD", "recorded_at is too old to accept.")

    # A retry after a lost response must not store the same fix twice.
    existing = db.scalar(
        select(LocationLog).where(
            LocationLog.dependent_id == dependent_id,
            LocationLog.recorded_at == at,
            LocationLog.lat == req.lat,
            LocationLog.lng == req.lng,
        )
    )
    rows = db.execute(
        select(LocationLog.lat, LocationLog.lng, LocationLog.recorded_at)
        .where(LocationLog.dependent_id == dependent_id, LocationLog.recorded_at < at)
        .order_by(LocationLog.recorded_at.desc())
        .limit(LOOKBACK_ROWS)
    ).all()
    state = classify_movement(req.lat, req.lng, at, [(r[0], r[1], r[2]) for r in rows], req.speed_mps, req.accuracy_m)

    if existing is not None:
        fence, _ = geofence_service.check_new_fix(db, dependent_id, existing, req.accuracy_m)
        low, _ = device_health_service.on_new_fix(db, dependent_id, existing)
        notification_service.dispatch_events_safely(db, dependent_id)
        return LocationAck(
            log_id=existing.log_id,
            recorded_at=existing.recorded_at,
            movement_state=state,
            next_update_interval_s=_wait_for(state, low),
            duplicate=True,
            geofence_status=fence,
            breach_started=False,  # a retry never reports a new breach
            low_battery=low,
            low_battery_started=False,
        )

    log = LocationLog(
        dependent_id=dependent_id, lat=req.lat, lng=req.lng, recorded_at=at, battery_level=req.battery_level
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    # FR-C2/C3: judge the fix against the safe zones (opens/closes a breach event when it changes).
    fence, started = geofence_service.check_new_fix(db, dependent_id, log, req.accuracy_m)
    # FR-L1/L2: battery alert, and a new fix proves the phone is back online.
    low, low_started = device_health_service.on_new_fix(db, dependent_id, log)
    # FR-M1: tell the Guardians now, not at the next scheduler tick.
    notification_service.dispatch_events_safely(db, dependent_id)
    return LocationAck(
        log_id=log.log_id,
        recorded_at=log.recorded_at,
        movement_state=state,
        next_update_interval_s=_wait_for(state, low),
        geofence_status=fence,
        breach_started=started,
        low_battery=low,
        low_battery_started=low_started,
    )


def _point(log: LocationLog) -> LocationPoint:
    return LocationPoint(lat=log.lat, lng=log.lng, recorded_at=log.recorded_at, battery_level=log.battery_level)


def latest(db: Session, dependent_id: uuid.UUID) -> LatestLocationOut:
    s = get_settings()
    log = db.scalar(
        select(LocationLog)
        .where(LocationLog.dependent_id == dependent_id)
        .order_by(LocationLog.recorded_at.desc())
        .limit(1)
    )
    if log is None:
        return LatestLocationOut(dependent_id=dependent_id, location=None, age_seconds=None, is_stale=True)
    age = max(0, int((datetime.now(timezone.utc) - log.recorded_at).total_seconds()))
    return LatestLocationOut(
        dependent_id=dependent_id, location=_point(log), age_seconds=age, is_stale=age > s.LOCATION_STALE_AFTER_S
    )


MAX_HISTORY = 500


def history(
    db: Session,
    dependent_id: uuid.UUID,
    start: datetime | None,
    end: datetime | None,
    limit: int,
) -> LocationHistoryOut:
    if start is not None and end is not None and start > end:
        raise AppError(422, "INVALID_RANGE", "'from' must be earlier than 'to'.")
    q = select(LocationLog).where(LocationLog.dependent_id == dependent_id)
    if start is not None:
        q = q.where(LocationLog.recorded_at >= start)
    if end is not None:
        q = q.where(LocationLog.recorded_at <= end)
    rows = db.scalars(q.order_by(LocationLog.recorded_at.desc()).limit(min(max(limit, 1), MAX_HISTORY))).all()
    return LocationHistoryOut(dependent_id=dependent_id, count=len(rows), points=[_point(r) for r in rows])
