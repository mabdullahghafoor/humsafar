"""
Remote Alarm Override router (Task 3.7, FR-D3).

SDS 11.1:  POST /dependents/{id}/alarm         sound the alarm on the Dependent's phone (PRIMARY Guardian only)
Added:     GET  /dependents/{id}/alarm         is it sounding? (the Primary, or the Dependent's phone)
           POST /dependents/{id}/alarm/stop    stop it (the Primary, or the Dependent)
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.alarm import AlarmIn, AlarmOut, AlarmStatusOut
from app.services import alarm_service

router = APIRouter(tags=["Remote alarm"])


@router.post("/dependents/{dependent_id}/alarm", response_model=AlarmOut, status_code=201)
def start_alarm(
    dependent_id: uuid.UUID,
    response: Response,
    body: AlarmIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out, created = alarm_service.trigger(db, user, dependent_id, body.duration_s if body else None)
    if not created:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/alarm", response_model=AlarmStatusOut)
def alarm_status(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return alarm_service.status(db, user, dependent_id)


@router.post("/dependents/{dependent_id}/alarm/stop", response_model=AlarmOut)
def stop_alarm(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return alarm_service.stop(db, user, dependent_id)
