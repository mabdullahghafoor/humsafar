"""
Voice and video call router (Task 4.4, FR-E2).

POST /calls                  start a call (rings the other person)
GET  /calls                  my call history (newest first, paged with `before`)
GET  /calls/{id}             state of one call (+ join info when allowed); the caller polls this while it rings
POST /calls/{id}/accept      the person being called accepts (they get the join info)
POST /calls/{id}/decline     the person being called says no
POST /calls/{id}/end         hang up (cancels a ringing call, ends an answered one)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.call import CallIn, CallList, CallOut
from app.services import call_service as svc

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post("", response_model=CallOut, status_code=201)
def start_call(body: CallIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = svc.start(db, user, body)
    if out.already_active:
        response.status_code = 200
    return out


@router.get("", response_model=CallList)
def call_history(
    limit: int = Query(30, ge=1, le=100), before: datetime | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return svc.history(db, user, limit=limit, before=before)


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get(db, user, call_id)


@router.post("/{call_id}/accept", response_model=CallOut)
def accept_call(call_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.accept(db, user, call_id)


@router.post("/{call_id}/decline", response_model=CallOut)
def decline_call(call_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.decline(db, user, call_id)


@router.post("/{call_id}/end", response_model=CallOut)
def end_call(call_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.end(db, user, call_id)
