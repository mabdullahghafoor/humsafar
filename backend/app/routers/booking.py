"""
Home-care booking requests and the shared Activity Timeline (Task 6.2, FR-J1, FR-I2/J2).

POST /dependents/{id}/bookings                         ask a listed provider for a visit
GET  /dependents/{id}/bookings                         list (filter status; paged; newest first)
GET  /dependents/{id}/bookings/{request_id}            one request
POST /dependents/{id}/bookings/{request_id}/confirm    pending -> confirmed
POST /dependents/{id}/bookings/{request_id}/complete   confirmed -> completed
POST /dependents/{id}/bookings/{request_id}/cancel     pending or confirmed -> cancelled
POST /dependents/{id}/directory/contacts               log "contacting this organization"
GET  /dependents/{id}/activity                         the unified Activity Timeline (filters type, from, to; paged)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.booking import ActivityList, ActivityOut, ActivityType, BookingIn, BookingList, BookingOut, BookingStatus, ContactIn
from app.services import booking_service as svc

router = APIRouter(tags=["Bookings and activity"])


@router.post("/dependents/{dependent_id}/bookings", response_model=BookingOut, status_code=201)
def create_booking(dependent_id: uuid.UUID, body: BookingIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = svc.create(db, user, dependent_id, body)
    if out.already_saved:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/bookings", response_model=BookingList)
def list_bookings(
    dependent_id: uuid.UUID,
    status: BookingStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_bookings(db, user, dependent_id, status=status, limit=limit, offset=offset)


@router.get("/dependents/{dependent_id}/bookings/{request_id}", response_model=BookingOut)
def get_booking(dependent_id: uuid.UUID, request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_one(db, user, dependent_id, request_id)


@router.post("/dependents/{dependent_id}/bookings/{request_id}/confirm", response_model=BookingOut)
def confirm_booking(dependent_id: uuid.UUID, request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.change_status(db, user, dependent_id, request_id, "confirmed")


@router.post("/dependents/{dependent_id}/bookings/{request_id}/complete", response_model=BookingOut)
def complete_booking(dependent_id: uuid.UUID, request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.change_status(db, user, dependent_id, request_id, "completed")


@router.post("/dependents/{dependent_id}/bookings/{request_id}/cancel", response_model=BookingOut)
def cancel_booking(dependent_id: uuid.UUID, request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.change_status(db, user, dependent_id, request_id, "cancelled")


@router.post("/dependents/{dependent_id}/directory/contacts", response_model=ActivityOut, status_code=201)
def log_contact(dependent_id: uuid.UUID, body: ContactIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out, created = svc.log_contact(db, user, dependent_id, body.org_id)
    if not created:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/activity", response_model=ActivityList)
def activity(
    dependent_id: uuid.UUID,
    type: ActivityType | None = Query(None),
    from_: datetime | None = Query(None, alias="from", description="Only entries at or after this time (with time zone)."),
    to: datetime | None = Query(None, description="Only entries at or before this time (with time zone)."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.timeline(db, user, dependent_id, type_=type, from_=from_, to=to, limit=limit, offset=offset)
