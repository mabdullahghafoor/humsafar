"""
Camera router (Task 6.3, FR-K1).

POST   /dependents/{id}/camera             pair the camera phone (Dependent or Primary)
GET    /dependents/{id}/camera             status: paired, online, viewers now
DELETE /dependents/{id}/camera             unpair (ends every viewing)
POST   /dependents/{id}/camera/heartbeat   the camera phone: "is anyone watching?" (Dependent's own device)
GET    /dependents/{id}/camera/stream      a Guardian starts or renews watching; returns the join token
DELETE /dependents/{id}/camera/stream      a Guardian stops watching
GET    /dependents/{id}/camera/viewing     the Dependent's "being viewed" indicator (FR-K1.3)
POST   /dependents/{id}/camera/clips/{clip_id}   the camera phone uploads an emergency clip (6.4, FR-K2)
GET    /dependents/{id}/camera/clips       list clips (Dependent, Primary, Secondary with camera_viewing)
GET    /dependents/{id}/camera/clips/{clip_id}         one clip's details
GET    /dependents/{id}/camera/clips/{clip_id}/video   download the video (decrypted; audited)
DELETE /dependents/{id}/camera/clips/{clip_id}         delete (Dependent or Primary)
"""

import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.core.config import get_settings
from app.schemas.camera import CameraPairIn, CameraStatus, ClipList, ClipOut, HeartbeatOut, StreamOut, ViewingOut
from typing import Literal
from app.services import camera_clip_service as clips, camera_service as svc

router = APIRouter(tags=["Camera"])

NO_STORE = {"Cache-Control": "private, no-store"}


@router.post("/dependents/{dependent_id}/camera", response_model=CameraStatus, status_code=201)
def pair(dependent_id: uuid.UUID, response: Response, body: CameraPairIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out, created = svc.pair(db, user, dependent_id, body or CameraPairIn())
    if not created:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/camera", response_model=CameraStatus)
def status(dependent_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.status(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/camera", status_code=204)
def unpair(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.unpair(db, user, dependent_id)
    return Response(status_code=204)


@router.post("/dependents/{dependent_id}/camera/heartbeat", response_model=HeartbeatOut)
def heartbeat(dependent_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.heartbeat(db, user, dependent_id)


@router.get("/dependents/{dependent_id}/camera/stream", response_model=StreamOut)
def start_stream(dependent_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.start_or_renew(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/camera/stream", status_code=204)
def stop_stream(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.stop(db, user, dependent_id)
    return Response(status_code=204)


@router.get("/dependents/{dependent_id}/camera/viewing", response_model=ViewingOut)
def viewing(dependent_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.viewing(db, user, dependent_id)


@router.post("/dependents/{dependent_id}/camera/clips/{clip_id}", response_model=ClipOut, status_code=201)
async def upload_clip(
    dependent_id: uuid.UUID, clip_id: uuid.UUID,
    file: UploadFile = File(..., description="MP4 or WebM video, up to 30 MB."),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    data = await file.read(get_settings().CLIP_MAX_BYTES + 1)  # never read more than the limit + 1 byte
    return await run_in_threadpool(clips.upload, db, user, dependent_id, clip_id, data)


@router.get("/dependents/{dependent_id}/camera/clips", response_model=ClipList)
def list_clips(
    dependent_id: uuid.UUID, response: Response, status: Literal["requested", "stored", "missed"] | None = None,
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    return clips.list_clips(db, user, dependent_id, status=status, limit=limit, offset=offset)


@router.get("/dependents/{dependent_id}/camera/clips/{clip_id}", response_model=ClipOut)
def get_clip(dependent_id: uuid.UUID, clip_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return clips.get_clip(db, user, dependent_id, clip_id)


@router.get("/dependents/{dependent_id}/camera/clips/{clip_id}/video")
def clip_video(dependent_id: uuid.UUID, clip_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data, ctype, name = clips.download(db, user, dependent_id, clip_id)
    return Response(data, media_type=ctype, headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{name}"'})


@router.delete("/dependents/{dependent_id}/camera/clips/{clip_id}", status_code=204)
def delete_clip(dependent_id: uuid.UUID, clip_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clips.delete(db, user, dependent_id, clip_id)
    return Response(status_code=204)
