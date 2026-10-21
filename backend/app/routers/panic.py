"""
Panic Mode router (Task 3.6, FR-D2).

SDS 11.1:  POST /dependents/{id}/panic            the Dependent presses the panic button (tells EVERY linked Guardian)
Added:     GET  /dependents/{id}/panic            is a panic open? (the Dependent, or any linked Guardian)
           POST /dependents/{id}/panic/resolve    close it: the Dependent ("I am safe") or the Primary Guardian
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.panic import PanicOut, PanicStatusOut
from app.services import panic_service

router = APIRouter(tags=["Panic Mode"])


@router.post("/dependents/{dependent_id}/panic", response_model=PanicOut, status_code=201)
def trigger_panic(dependent_id: uuid.UUID, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out, created = panic_service.trigger(db, user, dependent_id)
    if not created:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/panic", response_model=PanicStatusOut)
def panic_status(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return panic_service.status(db, user, dependent_id)


@router.post("/dependents/{dependent_id}/panic/resolve", response_model=PanicOut)
def resolve_panic(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return panic_service.resolve(db, user, dependent_id)
