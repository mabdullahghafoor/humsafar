"""
Camera router (Task 6.3, FR-K1).

POST   /dependents/{id}/camera             pair the camera phone (Dependent or Primary)
GET    /dependents/{id}/camera             status: paired, online, viewers now
DELETE /dependents/{id}/camera             unpair (ends every viewing)
POST   /dependents/{id}/camera/heartbeat   the camera phone: "is anyone watching?" (Dependent's own device)
GET    /dependents/{id}/camera/stream      a Guardian starts or renews watching; returns the join token
DELETE /dependents/{id}/camera/stream      a Guardian stops watching
GET    /dependents/{id}/camera/viewing     the Dependent's "being viewed" indicator (FR-K1.3)
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.camera import CameraPairIn, CameraStatus, HeartbeatOut, StreamOut, ViewingOut
from app.services import camera_service as svc

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
