"""
Wellness check router (Task 3.4, FR-D4).

SDS 11.1:  POST /dependents/{id}/wellness-checks                       configure check times (Guardian: Primary, or Secondary with emergency_alerts)
           POST /wellness-checks/{response_id}/respond                  the Dependent confirms they are OK
Added:     GET    /dependents/{id}/wellness-checks                     list (Dependent himself, or permitted Guardian)
           POST   /dependents/{id}/wellness-checks/default-schedule    08:00, 14:00, 20:00 if none exist yet
           PUT    /dependents/{id}/wellness-checks/{wc_id}             change time / grace period / on-off
           DELETE /dependents/{id}/wellness-checks/{wc_id}             switch off (history kept)
           GET    /dependents/{id}/wellness-check-responses            prompts and their results
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.wellness import (
    CheckResponseListOut,
    RespondOut,
    ResponseStatus,
    WellnessIn,
    WellnessListOut,
    WellnessOut,
    WellnessUpdate,
)
from app.services import wellness_service

router = APIRouter(tags=["Wellness check"])


@router.post("/dependents/{dependent_id}/wellness-checks", response_model=WellnessListOut, status_code=201)
def create_checks(
    dependent_id: uuid.UUID, body: WellnessIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Up to 3 active checks per Dependent. One row is created per time."""
    return wellness_service.create(db, user, dependent_id, body)


@router.post("/dependents/{dependent_id}/wellness-checks/default-schedule", response_model=WellnessListOut, status_code=201)
def create_default_checks(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The default schedule (08:00, 14:00, 20:00, 30 min grace). Only when no check exists yet."""
    return wellness_service.create_default(db, user, dependent_id)


@router.get("/dependents/{dependent_id}/wellness-checks", response_model=WellnessListOut)
def list_checks(
    dependent_id: uuid.UUID,
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return wellness_service.list_windows(db, user, dependent_id, include_inactive)


@router.put("/dependents/{dependent_id}/wellness-checks/{wc_id}", response_model=WellnessOut)
def update_check(
    dependent_id: uuid.UUID,
    wc_id: uuid.UUID,
    body: WellnessUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return wellness_service.update_window(db, user, dependent_id, wc_id, body)


@router.delete("/dependents/{dependent_id}/wellness-checks/{wc_id}", status_code=204)
def delete_check(
    dependent_id: uuid.UUID, wc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    wellness_service.deactivate(db, user, dependent_id, wc_id)
    return Response(status_code=204)


@router.get("/dependents/{dependent_id}/wellness-check-responses", response_model=CheckResponseListOut)
def list_responses(
    dependent_id: uuid.UUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    status: ResponseStatus | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Default range: the last 24 hours."""
    return wellness_service.list_responses(db, user, dependent_id, from_, to, status)


@router.post("/wellness-checks/{response_id}/respond", response_model=RespondOut)
def respond(response_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The Dependent taps 'I'm OK'. `response_id` comes from the prompt notification. Safe to repeat."""
    return wellness_service.respond(db, user, response_id)
