"""
Appointment tracker router (Task 5.1, FR-G4).

POST   /dependents/{id}/appointments                          add (the Dependent or a permitted Guardian)
GET    /dependents/{id}/appointments?when=upcoming|past|all   list
GET    /dependents/{id}/appointments/{appointment_id}         one
PATCH  /dependents/{id}/appointments/{appointment_id}         change the doctor, the time or the note
POST   /dependents/{id}/appointments/{appointment_id}/cancel  cancel (kept in the history)
DELETE /dependents/{id}/appointments/{appointment_id}         remove completely
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.appointment import AppointmentIn, AppointmentList, AppointmentOut, AppointmentUpdate
from app.services import appointments_service as svc

router = APIRouter(tags=["Appointments"])


@router.post("/dependents/{dependent_id}/appointments", response_model=AppointmentOut, status_code=201)
def add_appointment(dependent_id: uuid.UUID, body: AppointmentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.create(db, user, dependent_id, body)


@router.get("/dependents/{dependent_id}/appointments", response_model=AppointmentList)
def list_appointments(
    dependent_id: uuid.UUID,
    when: Literal["upcoming", "past", "all"] = "upcoming",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_appointments(db, user, dependent_id, when=when, limit=limit, offset=offset)


@router.get("/dependents/{dependent_id}/appointments/{appointment_id}", response_model=AppointmentOut)
def get_appointment(dependent_id: uuid.UUID, appointment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_one(db, user, dependent_id, appointment_id)


@router.patch("/dependents/{dependent_id}/appointments/{appointment_id}", response_model=AppointmentOut)
def change_appointment(
    dependent_id: uuid.UUID, appointment_id: uuid.UUID, body: AppointmentUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.update(db, user, dependent_id, appointment_id, body)


@router.post("/dependents/{dependent_id}/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(dependent_id: uuid.UUID, appointment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.cancel(db, user, dependent_id, appointment_id)


@router.delete("/dependents/{dependent_id}/appointments/{appointment_id}", status_code=204)
def delete_appointment(dependent_id: uuid.UUID, appointment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete(db, user, dependent_id, appointment_id)
    return Response(status_code=204)
