"""
Geofences and breach detection (Task 2.2, FR-C2 / FR-C3).

Rules:
  * Only the Dependent's verified Primary Guardian creates, changes or deletes zones (FR-C2.1).
    Anyone who may see the live location (Primary, or a Secondary with `live_location`) may read them.
  * A Dependent has between 0 and MAX_ZONES zones (FR-C3.1). With no zone there is nothing to breach.
  * Inside ANY zone = safe. Outside ALL zones = breach (FR-C3.2).
  * GPS error: a fix counts as inside if it is within radius + accuracy (accuracy capped at 100 m), so a
    noisy fix near the border does not raise a false alarm.
  * One breach = one `escalation_events` row (trigger_type 'geofence_breach'), opened when the Dependent
    goes from safe to outside and resolved when they are back inside (or the zones are removed).
    Repeated fixes while outside do NOT create more events (no alert spam).
  * Only the NEWEST fix decides. A late-arriving buffered fix from earlier cannot flip the state.
  * Sending the alert to Guardians is the notification service (Task 3.1). Until then the open
    `escalation_events` row is the signal that 3.1 will pick up.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.geo import haversine_m
from app.models import EscalationEvent, Geofence, LocationLog, User
from app.schemas.geofence import GeofenceIn, GeofenceListOut, GeofenceOut, GeofenceStatusOut
from app.services import linkage_service, permission_service

MAX_ZONES = 10
BREACH = "geofence_breach"
OPEN, RESOLVED = "open", "resolved"
MAX_ACCURACY_ALLOWANCE_M = 100.0


def _out(g: Geofence) -> GeofenceOut:
    return GeofenceOut(
        geofence_id=g.geofence_id,
        dependent_id=g.dependent_id,
        name=g.name,
        lat=g.lat,
        lng=g.lng,
        radius_m=g.radius_m,
        created_by=g.created_by,
    )


def _zones(db: Session, dependent_id: uuid.UUID) -> list[Geofence]:
    return list(db.scalars(select(Geofence).where(Geofence.dependent_id == dependent_id).order_by(Geofence.name)))


# ---------------------------------------------------------------- pure logic

def evaluate(zones: list[Geofence], lat: float, lng: float, accuracy_m: float | None = None) -> tuple[str, list[uuid.UUID]]:
    """Returns ('no_zones' | 'inside' | 'outside', ids of the zones the point is inside)."""
    if not zones:
        return "no_zones", []
    allowance = min(accuracy_m or 0.0, MAX_ACCURACY_ALLOWANCE_M)
    inside = [z.geofence_id for z in zones if haversine_m(lat, lng, z.lat, z.lng) <= z.radius_m + allowance]
    return ("inside" if inside else "outside"), inside


# ------------------------------------------------------------------- CRUD

def _check_zone_exists(db: Session, dependent_id: uuid.UUID, geofence_id: uuid.UUID) -> Geofence:
    g = db.get(Geofence, geofence_id)
    # A zone id that belongs to another Dependent looks exactly like a missing one.
    if g is None or g.dependent_id != dependent_id:
        raise AppError(404, "GEOFENCE_NOT_FOUND", "No such geofence for this Dependent.")
    return g


def create(db: Session, user: User, dependent_id: uuid.UUID, body: GeofenceIn) -> GeofenceOut:
    permission_service._require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)  # two simultaneous creates cannot both pass the limit
    if len(_zones(db, dependent_id)) >= MAX_ZONES:
        raise AppError(409, "GEOFENCE_LIMIT_REACHED", f"A Dependent can have at most {MAX_ZONES} zones.", {"max": MAX_ZONES})
    g = Geofence(
        dependent_id=dependent_id, name=body.name, lat=body.lat, lng=body.lng, radius_m=body.radius_m, created_by=user.user_id
    )
    db.add(g)
    db.flush()
    reevaluate(db, dependent_id)
    db.commit()
    db.refresh(g)
    return _out(g)


def update(db: Session, user: User, dependent_id: uuid.UUID, geofence_id: uuid.UUID, body: GeofenceIn) -> GeofenceOut:
    permission_service._require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    g = _check_zone_exists(db, dependent_id, geofence_id)
    g.name, g.lat, g.lng, g.radius_m = body.name, body.lat, body.lng, body.radius_m
    db.flush()
    reevaluate(db, dependent_id)
    db.commit()
    db.refresh(g)
    return _out(g)


def delete(db: Session, user: User, dependent_id: uuid.UUID, geofence_id: uuid.UUID) -> None:
    permission_service._require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    g = _check_zone_exists(db, dependent_id, geofence_id)
    db.delete(g)
    db.flush()
    reevaluate(db, dependent_id)
    db.commit()


def list_zones(db: Session, dependent_id: uuid.UUID) -> GeofenceListOut:
    zs = _zones(db, dependent_id)
    return GeofenceListOut(dependent_id=dependent_id, count=len(zs), max_zones=MAX_ZONES, geofences=[_out(z) for z in zs])


# ---------------------------------------------------------------- breach state

def _open_event(db: Session, dependent_id: uuid.UUID, lock: bool = False) -> EscalationEvent | None:
    q = select(EscalationEvent).where(
        EscalationEvent.dependent_id == dependent_id,
        EscalationEvent.trigger_type == BREACH,
        EscalationEvent.status == OPEN,
    )
    if lock:
        q = q.with_for_update()
    return db.scalars(q.order_by(EscalationEvent.created_at.desc())).first()


def sync_breach_state(db: Session, dependent_id: uuid.UUID, state: str, allow_open: bool = True) -> bool:
    """
    Make the open breach event match `state`. Returns True only when a NEW breach was opened.
    The Dependent row is locked before changing anything, so two simultaneous requests cannot
    both open a breach (or both resolve one). Does not commit; the caller does.
    """
    needs_open = state == "outside" and allow_open
    needs_close = state in ("inside", "no_zones")
    if not (needs_open or needs_close):
        return False
    if (_open_event(db, dependent_id) is not None) == needs_open:
        return False  # already in the right state: the common case, no lock taken

    linkage_service._lock_dependent(db, dependent_id)
    existing = _open_event(db, dependent_id, lock=True)
    if needs_open:
        if existing is not None:
            return False
        db.add(EscalationEvent(dependent_id=dependent_id, trigger_type=BREACH, tier="primary", status=OPEN))
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


def reevaluate(db: Session, dependent_id: uuid.UUID) -> None:
    """
    Zones changed: judge the newest known position against the new zone set. A stale position
    can close a breach (zones removed) but is never used to open a new one.
    """
    log = _latest_log(db, dependent_id)
    if log is None:
        return
    state, _ = evaluate(_zones(db, dependent_id), log.lat, log.lng)
    age = (datetime.now(timezone.utc) - log.recorded_at).total_seconds()
    sync_breach_state(db, dependent_id, state, allow_open=age <= get_settings().LOCATION_STALE_AFTER_S)


def check_new_fix(db: Session, dependent_id: uuid.UUID, log: LocationLog, accuracy_m: float | None) -> tuple[str, bool]:
    """
    Called by the location ingest after a fix is stored. Returns (state, breach_started).
    A fix that is not the newest one (a late buffered upload) is not allowed to change the state.
    """
    newest = _latest_log(db, dependent_id)
    state, _ = evaluate(_zones(db, dependent_id), log.lat, log.lng, accuracy_m)
    if newest is not None and newest.log_id != log.log_id and newest.recorded_at > log.recorded_at:
        return state, False
    started = sync_breach_state(db, dependent_id, state)
    db.commit()
    return state, started


def status(db: Session, dependent_id: uuid.UUID) -> GeofenceStatusOut:
    log = _latest_log(db, dependent_id)
    ev = _open_event(db, dependent_id)
    inside: list[uuid.UUID] = []
    if log is None:
        state = "unknown"
    else:
        state, inside = evaluate(_zones(db, dependent_id), log.lat, log.lng)
        stale = (datetime.now(timezone.utc) - log.recorded_at).total_seconds() > get_settings().LOCATION_STALE_AFTER_S
        if stale and state != "no_zones":
            state = "unknown"  # too old to say where they are now
    return GeofenceStatusOut(
        dependent_id=dependent_id,
        status=state,
        inside_zone_ids=inside if state == "inside" else [],
        breach_open=ev is not None,
        breach_event_id=ev.event_id if ev else None,
        breach_since=ev.created_at if ev else None,
    )
