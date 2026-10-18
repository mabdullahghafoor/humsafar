"""
External emergency contact router (Task 3.8, FR-R1).

PUT    /dependents/{id}/emergency-contact   set / replace the ONE contact (Primary Guardian only)
GET    /dependents/{id}/emergency-contact   read it (the Primary, or a Secondary with emergency_alerts)
DELETE /dependents/{id}/emergency-contact   remove it (Primary Guardian only)
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.emergency_contact import ContactIn, ContactOut
from app.services import emergency_contact_service as svc

router = APIRouter(tags=["Emergency contact"])


@router.put("/dependents/{dependent_id}/emergency-contact", response_model=ContactOut)
def put_contact(dependent_id: uuid.UUID, body: ContactIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.put(db, user, dependent_id, body)


@router.get("/dependents/{dependent_id}/emergency-contact", response_model=ContactOut)
def get_contact(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.read(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/emergency-contact", status_code=204)
def delete_contact(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete(db, user, dependent_id)
    return Response(status_code=204)
