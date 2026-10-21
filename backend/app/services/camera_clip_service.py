"""
Event-triggered clip capture (Task 6.4, FR-K2).

When Panic Mode (3.6) or the Remote Alarm (3.7) starts and the Dependent has a paired camera, a clip *request* is saved. The server
cannot record a hosted video room (clarification 141), so the camera phone does the recording:
  1. its next heartbeat carries `clip` (record N seconds now),
  2. it uploads the file: POST /dependents/{id}/camera/clips/{clip_id},
  3. the server checks it is a real video, stores it encrypted (FR-N2, same cipher as the vault) and tells the family.
A request not fulfilled within CLIP_REQUEST_TTL_S becomes `missed` (the list says so, so nobody wonders why there is no clip).
Who may see clips: the Dependent, the Primary, and a Secondary with `camera_viewing`. Every Guardian download is audited (FR-N3).
Starting a clip request must never get in the way of the emergency itself: it never raises.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, CameraClip, CameraDevice, User
from app.schemas.camera import ClipList, ClipOut, ClipTask
from app.services import crypto_service, linkage_service, permission_service, storage_service
from app.services import notification_service as ns

log = logging.getLogger("humsafar.clips")
MODULE = "camera_viewing"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _out(c: CameraClip) -> ClipOut:
    return ClipOut(
        clip_id=c.clip_id, dependent_id=c.dependent_id, trigger_type=c.trigger_type, status=c.status, event_id=c.event_id, captured_at=c.captured_at,
        duration_s=c.duration_s, uploaded_at=c.uploaded_at, size_bytes=c.size_bytes, content_type=c.content_type,
    )


# ------------------------------------------------------------------ the emergency starts: ask the camera phone to record

def request_for_event(db: Session, dependent_id: uuid.UUID, trigger_type: str, event_id: uuid.UUID) -> None:
    """Called after Panic Mode / Remote Alarm has been saved. Never raises. No camera paired = nothing to do."""
    try:
        s = get_settings()
        if db.scalar(select(CameraDevice.camera_id).where(CameraDevice.dependent_id == dependent_id)) is None:
            return
        stored = db.scalar(select(func.count()).select_from(CameraClip).where(CameraClip.dependent_id == dependent_id, CameraClip.status == "stored")) or 0
        if stored >= s.CLIPS_MAX_PER_DEPENDENT:
            log.warning("clip not requested for %s: storage cap reached", dependent_id)
            return
        now = _now()
        db.add(CameraClip(
            dependent_id=dependent_id, trigger_type=trigger_type, event_id=event_id, status="requested", captured_at=now,
            duration_s=s.CLIP_DURATION_S, expires_at=now + timedelta(seconds=s.CLIP_REQUEST_TTL_S),
        ))
        db.commit()
    except IntegrityError:
        db.rollback()  # the same event already has its clip request
    except Exception:  # noqa: BLE001 - an emergency must never fail because of the camera
        db.rollback()
        log.exception("clip request failed for %s", dependent_id)


def pending_task(db: Session, dependent_id: uuid.UUID, now: datetime) -> ClipTask | None:
    """The oldest request the camera phone should record now. Marks the ones that ran out as missed (flush only)."""
    task = None
    for c in db.scalars(select(CameraClip).where(CameraClip.dependent_id == dependent_id, CameraClip.status == "requested").order_by(CameraClip.captured_at)).all():
        if c.expires_at is not None and c.expires_at <= now:
            c.status = "missed"
            continue
        if task is None:
            task = ClipTask(clip_id=c.clip_id, trigger_type=c.trigger_type, duration_s=c.duration_s or get_settings().CLIP_DURATION_S, requested_at=c.captured_at, expires_at=c.expires_at)
    db.flush()
    return task


def miss_pending(db: Session, dependent_id: uuid.UUID, now: datetime) -> None:
    for c in db.scalars(select(CameraClip).where(CameraClip.dependent_id == dependent_id, CameraClip.status == "requested")).all():
        c.status = "missed"


def sweep(db: Session) -> int:
    """Every minute: requests nobody fulfilled in time become `missed`."""
    n = 0
    for c in db.scalars(select(CameraClip).where(CameraClip.status == "requested", CameraClip.expires_at <= _now()).with_for_update(skip_locked=True)).all():
        c.status = "missed"
        n += 1
    db.commit()
    return n


# ------------------------------------------------------------------ upload by the camera phone

def sniff(data: bytes) -> tuple[str, str] | None:
    """(content type, extension) from the first bytes: MP4 ('ftyp' box) or WebM (EBML header)."""
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4", ".mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", ".webm"
    return None


def upload(db: Session, user: User, dependent_id: uuid.UUID, clip_id: uuid.UUID, data: bytes) -> ClipOut:
    s = get_settings()
    if user.role != "dependent" or user.user_id != dependent_id:
        raise AppError(403, "FORBIDDEN", "Only the Dependent's own camera phone can upload a clip.")
    if len(data) > s.CLIP_MAX_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", f"The clip is too big (limit {s.CLIP_MAX_BYTES // 1_000_000} MB).")
    kind = sniff(data)
    if not data or kind is None:
        raise AppError(415, "UNSUPPORTED_FILE", "Only MP4 or WebM video is accepted.")
    c = db.scalar(select(CameraClip).where(CameraClip.clip_id == clip_id, CameraClip.dependent_id == dependent_id))
    if c is None:
        raise AppError(404, "CLIP_NOT_FOUND", "This clip request does not exist.")
    db.rollback()
    store = storage_service.get_storage("clips")
    key = store.save(crypto_service.encrypt(data), ".bin")
    try:
        linkage_service._lock_dependent(db, dependent_id)
        c = db.scalar(select(CameraClip).where(CameraClip.clip_id == clip_id).with_for_update())
        now = _now()
        if c.status == "stored":
            raise AppError(409, "CLIP_ALREADY_STORED", "This clip was already uploaded.")
        if c.status == "missed" or (c.expires_at is not None and c.expires_at <= now):
            c.status = "missed"
            db.commit()
            raise AppError(409, "CLIP_EXPIRED", "The time to upload this clip has passed.")
        c.status, c.file_url, c.uploaded_at, c.size_bytes, c.content_type = "stored", key, now, len(data), kind[0]
        db.add(AuditLog(actor_id=user.user_id, action="camera_clip_stored", target_type="camera_clip", target_id=c.clip_id))
        db.commit()
    except Exception:
        db.rollback()
        store.delete(key)
        raise
    db.refresh(c)
    _tell(db, c)
    return _out(c)


def _tell(db: Session, c: CameraClip) -> None:
    what = "Panic Mode" if c.trigger_type == "panic" else "the Remote Alarm"
    try:
        for uid in ns.recipients(db, c.dependent_id, ns.LINKED_PERMITTED, module=MODULE):
            ns.notify(db, uid, "camera_clip", ns.STANDARD, "Camera clip saved", f"A short clip was recorded when {what} started.",
                      dependent_id=c.dependent_id, dedupe_key=f"camera_clip:{c.clip_id}", extra={"clip_id": str(c.clip_id), "trigger_type": c.trigger_type})
    except Exception:  # noqa: BLE001 - the clip is saved; a notice failing must not undo it
        db.rollback()
        log.exception("clip notice failed")


# ------------------------------------------------------------------ the family

def _authorize(db: Session, user: User, dependent_id: uuid.UUID) -> bool:
    """True for a Guardian (reads are audited), False for the Dependent herself."""
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return False
    permission_service.check_module_access(db, user, dependent_id, MODULE)
    return True


def list_clips(db: Session, user: User, dependent_id: uuid.UUID, *, status: str | None, limit: int, offset: int) -> ClipList:
    _authorize(db, user, dependent_id)
    q = select(CameraClip).where(CameraClip.dependent_id == dependent_id)
    if status:
        q = q.where(CameraClip.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(CameraClip.captured_at.desc(), CameraClip.clip_id).limit(limit).offset(offset)).all()
    return ClipList(items=[_out(c) for c in rows], total=total, limit=limit, offset=offset)


def _get(db: Session, dependent_id: uuid.UUID, clip_id: uuid.UUID) -> CameraClip:
    c = db.scalar(select(CameraClip).where(CameraClip.clip_id == clip_id, CameraClip.dependent_id == dependent_id))
    if c is None:
        raise AppError(404, "CLIP_NOT_FOUND", "This clip does not exist.")
    return c


def get_clip(db: Session, user: User, dependent_id: uuid.UUID, clip_id: uuid.UUID) -> ClipOut:
    _authorize(db, user, dependent_id)
    return _out(_get(db, dependent_id, clip_id))


def download(db: Session, user: User, dependent_id: uuid.UUID, clip_id: uuid.UUID) -> tuple[bytes, str, str]:
    """(video bytes, content type, file name). A Guardian's download is written to the audit log (FR-N3)."""
    guardian = _authorize(db, user, dependent_id)
    c = _get(db, dependent_id, clip_id)
    path = storage_service.get_storage("clips").path(c.file_url) if c.file_url else None
    if c.status != "stored" or path is None:
        raise AppError(404, "CLIP_NOT_FOUND", "This clip has no video.")
    try:
        data = crypto_service.decrypt(path.read_bytes())
    except crypto_service.DecryptError:
        raise AppError(500, "CLIP_UNREADABLE", "This clip could not be read.")
    if guardian:
        db.add(AuditLog(actor_id=user.user_id, action="camera_clip_viewed", target_type="camera_clip", target_id=c.clip_id))
        db.commit()
    ext = ".mp4" if c.content_type == "video/mp4" else ".webm"
    return data, c.content_type, f"clip-{c.captured_at:%Y%m%d-%H%M%S}{ext}"


def delete(db: Session, user: User, dependent_id: uuid.UUID, clip_id: uuid.UUID) -> None:
    """The Dependent or the Primary removes a clip (file and row). Safe to repeat."""
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    elif not (user.role == "guardian" and linkage_service._is_primary_of(db, user.user_id, dependent_id)):
        permission_service.check_module_access(db, user, dependent_id, MODULE)  # explains NOT_LINKED etc. first
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can delete a clip.")
    c = db.scalar(select(CameraClip).where(CameraClip.clip_id == clip_id, CameraClip.dependent_id == dependent_id).with_for_update())
    if c is None:
        db.rollback()
        return
    key = c.file_url
    db.delete(c)
    db.add(AuditLog(actor_id=user.user_id, action="camera_clip_deleted", target_type="camera_clip", target_id=clip_id))
    db.commit()
    if key:
        storage_service.get_storage("clips").delete(key)
