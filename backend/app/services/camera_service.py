"""
Camera: pairing and on-demand live viewing (Task 6.3, FR-K1; the encryption statement is clarification 140).

Design (clarifications 134 to 141):
  * The camera is a spare Android phone in "camera mode" (hardware decision). It is logged in as the Dependent's account.
    The video does NOT pass through our server: the camera phone publishes into a hosted RTC room (the same provider as calls,
    ZegoCloud) and the Guardian's app plays it. Our server only decides who may join which room, with a short token
    (a viewer's token cannot publish).
  * On demand: the camera phone asks "is anyone watching?" every few seconds (heartbeat). It publishes only while a Guardian has an
    open viewing session; otherwise it stays dark (privacy and battery).
  * Gate: the Primary always; a Secondary needs `camera_viewing` (FR-A4), checked on every request and again when a session is renewed,
    and a session whose viewer lost the permission is closed on the spot. The Dependent never watches their own camera through this.
  * Viewing indicator (FR-K1.3): while a session is open, the Dependent's phone can read `GET .../camera/viewing` (who is watching) and gets a
    `camera_view` notification when a new session starts; the Primary is told when a Secondary watches.
  * A session lasts CAMERA_SESSION_TTL_S unless the viewer renews it (calls GET .../camera/stream again). A dead app therefore stops
    "viewing" by itself, and the background job closes it.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, CameraDevice, CameraSession, GuardianDependentLink, User
from app.schemas.camera import CameraPairIn, ClipTask, CameraStatus, HeartbeatOut, RoomJoin, StreamOut, Viewer, ViewingOut
from app.services import call_provider, camera_clip_service as clip_service, linkage_service, permission_service
from app.services import notification_service as ns

log = logging.getLogger("humsafar.camera")
MODULE = "camera_viewing"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, actor_id: uuid.UUID, action: str, target_type: str, target_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id))


def _camera(db: Session, dependent_id: uuid.UUID) -> CameraDevice | None:
    return db.scalar(select(CameraDevice).where(CameraDevice.dependent_id == dependent_id))


def _need_camera(db: Session, dependent_id: uuid.UUID) -> CameraDevice:
    cam = _camera(db, dependent_id)
    if cam is None:
        raise AppError(409, "NO_CAMERA", "No camera is paired for this Dependent.")
    return cam


def _online(cam: CameraDevice, now: datetime) -> bool:
    return cam.last_seen_at is not None and cam.last_seen_at >= now - timedelta(seconds=get_settings().CAMERA_ONLINE_S)


def _is_self_or_primary(db: Session, user: User, dependent_id: uuid.UUID) -> bool:
    if user.role == "dependent":
        return user.user_id == dependent_id
    return user.role == "guardian" and linkage_service._is_primary_of(db, user.user_id, dependent_id)


def _only_dependent(user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "Only the Dependent's own device can do this.")


def _join(cam: CameraDevice, uid: str, *, publish: bool, ttl_s: int) -> RoomJoin | None:
    room = cam.stream_uri.removeprefix("rtc:")
    tok = call_provider.room_token(room, uid, publish=publish, ttl_s=ttl_s)
    return RoomJoin(**tok, stream_id=f"{room}-stream") if tok else None


def _end(db: Session, s: CameraSession, reason: str, now: datetime) -> None:
    s.ended_at = now
    s.end_reason = reason
    _audit(db, s.viewer_id, "camera_view_ended", "camera_session", s.session_id)


def _live_sessions(db: Session, dependent_id: uuid.UUID, now: datetime) -> list[CameraSession]:
    """The open sessions that are still valid. Closes (no commit) the expired ones and those whose viewer lost the permission."""
    live = []
    for s in db.scalars(select(CameraSession).where(CameraSession.dependent_id == dependent_id, CameraSession.ended_at.is_(None)).order_by(CameraSession.started_at)).all():
        if s.expires_at <= now:
            _end(db, s, "expired", now)
            continue
        viewer = db.get(User, s.viewer_id)
        try:
            if viewer is None:
                raise AppError(403, "FORBIDDEN", "gone")
            permission_service.check_module_access(db, viewer, dependent_id, MODULE)
        except AppError:
            _end(db, s, "permission_revoked", now)
            continue
        live.append(s)
    db.flush()
    return live


# ------------------------------------------------------------------ pairing

def pair(db: Session, user: User, dependent_id: uuid.UUID, body: CameraPairIn) -> tuple[CameraStatus, bool]:
    """The Dependent (the camera phone) or the Primary pairs the camera. Returns (status, created)."""
    if not _is_self_or_primary(db, user, dependent_id):
        raise AppError(403, "FORBIDDEN", "Only the Dependent or the Primary Guardian can pair the camera.")
    linkage_service._lock_dependent(db, dependent_id)
    cam = _camera(db, dependent_id)
    created = cam is None
    if created:
        cam = CameraDevice(dependent_id=dependent_id, stream_uri=f"rtc:cam-{dependent_id.hex}", name=body.name)
        db.add(cam)
        _audit(db, user.user_id, "camera_paired", "camera_device", dependent_id)
    elif body.name is not None:
        cam.name = body.name
    db.commit()
    db.refresh(cam)
    return _status_of(db, cam, dependent_id), created


def unpair(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    if not _is_self_or_primary(db, user, dependent_id):
        raise AppError(403, "FORBIDDEN", "Only the Dependent or the Primary Guardian can unpair the camera.")
    linkage_service._lock_dependent(db, dependent_id)
    cam = _camera(db, dependent_id)
    if cam is None:
        db.rollback()
        return
    now = _now()
    for s in db.scalars(select(CameraSession).where(CameraSession.dependent_id == dependent_id, CameraSession.ended_at.is_(None))).all():
        _end(db, s, "unpaired", now)
    clip_service.miss_pending(db, dependent_id, now)
    db.delete(cam)
    _audit(db, user.user_id, "camera_unpaired", "camera_device", dependent_id)
    db.commit()


def _status_of(db: Session, cam: CameraDevice | None, dependent_id: uuid.UUID) -> CameraStatus:
    S = get_settings()
    now = _now()
    if cam is None:
        return CameraStatus(paired=False, online=False, viewers_now=0, max_viewers=S.CAMERA_MAX_VIEWERS)
    viewers = len(_live_sessions(db, dependent_id, now))
    db.commit()
    return CameraStatus(
        paired=True, camera_id=cam.camera_id, name=cam.name, paired_at=cam.paired_at, online=_online(cam, now),
        last_seen_at=cam.last_seen_at, viewers_now=viewers, max_viewers=S.CAMERA_MAX_VIEWERS,
    )


def status(db: Session, user: User, dependent_id: uuid.UUID) -> CameraStatus:
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    else:
        permission_service.check_module_access(db, user, dependent_id, MODULE)
    return _status_of(db, _camera(db, dependent_id), dependent_id)


# ------------------------------------------------------------------ the camera phone

def heartbeat(db: Session, user: User, dependent_id: uuid.UUID) -> HeartbeatOut:
    S = get_settings()
    _only_dependent(user, dependent_id)
    cam = _need_camera(db, dependent_id)
    now = _now()
    cam.last_seen_at = now
    live = _live_sessions(db, dependent_id, now)
    task = clip_service.pending_task(db, dependent_id, now)  # FR-K2: an emergency clip is waiting to be recorded
    db.commit()
    poll = S.CAMERA_POLL_ACTIVE_S if (live or task) else S.CAMERA_POLL_IDLE_S
    if not live:
        return HeartbeatOut(should_publish=False, viewers_now=0, next_poll_s=poll, clip=task)
    join = _join(cam, f"camera-{dependent_id}", publish=True, ttl_s=S.CALL_TOKEN_TTL_S)
    return HeartbeatOut(should_publish=True, viewers_now=len(live), next_poll_s=poll, join=join, clip=task)


# ------------------------------------------------------------------ the Guardian

def start_or_renew(db: Session, user: User, dependent_id: uuid.UUID) -> StreamOut:
    S = get_settings()
    permission_service.check_module_access(db, user, dependent_id, MODULE)  # Primary always; a Secondary needs camera_viewing
    cam = _need_camera(db, dependent_id)
    now = _now()
    if not _online(cam, now):
        raise AppError(409, "CAMERA_OFFLINE", "The camera phone is not connected right now.", {"last_seen_at": cam.last_seen_at.isoformat() if cam.last_seen_at else None})
    join = _join(cam, str(user.user_id), publish=False, ttl_s=S.CAMERA_SESSION_TTL_S)
    if join is None:
        raise AppError(503, "STREAM_PROVIDER_UNAVAILABLE", "The video service could not be reached. Try again in a moment.")

    linkage_service._lock_dependent(db, dependent_id)  # one viewer at a time decides about the viewer limit
    live = _live_sessions(db, dependent_id, now)
    mine = next((s for s in live if s.viewer_id == user.user_id), None)
    renewed = mine is not None
    if mine is None:
        if len(live) >= S.CAMERA_MAX_VIEWERS:
            db.commit()
            raise AppError(409, "TOO_MANY_VIEWERS", f"At most {S.CAMERA_MAX_VIEWERS} people can watch at the same time.")
        mine = CameraSession(dependent_id=dependent_id, viewer_id=user.user_id, started_at=now, last_renewed_at=now, expires_at=now + timedelta(seconds=S.CAMERA_SESSION_TTL_S))
        db.add(mine)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise AppError(409, "CONFLICT", "Another request for the same viewing is in progress. Try again.")
        _audit(db, user.user_id, "camera_view_started", "camera_session", mine.session_id)
    else:
        mine.last_renewed_at = now
        mine.expires_at = now + timedelta(seconds=S.CAMERA_SESSION_TTL_S)
    db.commit()
    db.refresh(mine)
    if not renewed:
        _tell(db, user, mine)
    return StreamOut(
        session_id=mine.session_id, dependent_id=dependent_id, camera_name=cam.name, started_at=mine.started_at, expires_at=mine.expires_at,
        renew_every_s=max(5, S.CAMERA_SESSION_TTL_S // 3), join=join, renewed=renewed,
    )


def _tell(db: Session, viewer: User, s: CameraSession) -> None:
    """The viewing notice: the Dependent always; the Primary too when someone else watches."""
    who = viewer.full_name or "A Guardian"
    name = ns._display_name(db, s.dependent_id)
    extra = {"session_id": str(s.session_id), "viewer_id": str(viewer.user_id)}
    ns.notify(db, s.dependent_id, "camera_view", ns.STANDARD, "Camera is being viewed", f"{who} is watching your camera.", dependent_id=s.dependent_id, dedupe_key=f"camera_session:{s.session_id}", extra=extra)
    for uid in ns.recipients(db, s.dependent_id, ns.BY_TIER, "primary"):
        if uid != viewer.user_id:
            ns.notify(db, uid, "camera_view", ns.STANDARD, "Camera is being viewed", f"{who} is watching {name}'s camera.", dependent_id=s.dependent_id, dedupe_key=f"camera_session:{s.session_id}", extra=extra)


def stop(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    """Close my own open viewing. Safe to repeat. Needs no permission (leaving is always allowed)."""
    now = _now()
    linkage_service._lock_dependent(db, dependent_id)
    for s in db.scalars(select(CameraSession).where(CameraSession.dependent_id == dependent_id, CameraSession.viewer_id == user.user_id, CameraSession.ended_at.is_(None))).all():
        _end(db, s, "stopped", now)
    db.commit()


# ------------------------------------------------------------------ the Dependent's indicator (FR-K1.3)

def viewing(db: Session, user: User, dependent_id: uuid.UUID) -> ViewingOut:
    _only_dependent(user, dependent_id)
    live = _live_sessions(db, dependent_id, _now())
    db.commit()
    roles = {l.guardian_id: l.role for l in db.scalars(select(GuardianDependentLink).where(GuardianDependentLink.dependent_id == dependent_id)).all()}
    out = []
    for s in live:
        u = db.get(User, s.viewer_id)
        out.append(Viewer(user_id=s.viewer_id, full_name=(u.full_name if u else "") or "A Guardian", role="primary" if roles.get(s.viewer_id) == "primary" else "secondary", since=s.started_at))
    return ViewingOut(being_viewed=bool(out), viewers=out)


# ------------------------------------------------------------------ background job

def sweep(db: Session) -> int:
    """Every minute: close viewing sessions that ran out or whose viewer lost the permission."""
    n = 0
    for dep_id in db.scalars(select(CameraSession.dependent_id).where(CameraSession.ended_at.is_(None)).distinct()).all():
        before = db.scalar(select(func.count()).select_from(CameraSession).where(CameraSession.dependent_id == dep_id, CameraSession.ended_at.is_(None))) or 0
        live = _live_sessions(db, dep_id, _now())
        db.commit()
        n += before - len(live)
    return n
