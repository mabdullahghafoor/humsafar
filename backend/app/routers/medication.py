"""
Medication router (Task 3.2, FR-F1).

SDS 11.1:  POST /dependents/{id}/medications               create a schedule (Guardian: Primary, or Secondary with medication_management)
           POST /medications/{schedule_id}/confirm         confirm a dose taken (Dependent), step 2 of 2
Added:     GET    /dependents/{id}/medications             list schedules (Dependent himself, or permitted Guardian)
           PUT    /dependents/{id}/medications/{schedule_id}    change a schedule
           DELETE /dependents/{id}/medications/{schedule_id}    switch a schedule off (history is kept)
           GET    /dependents/{id}/medication-doses        dose history and upcoming doses
           POST   /medications/{schedule_id}/confirm-request    step 1 of 2 (Dependent)
Task 3.3:  POST /dependents/{id}/medication-doses/{confirmation_id}/extend     give more time (Guardian)
           POST /dependents/{id}/medication-doses/{confirmation_id}/escalate  alert the Secondaries now (Guardian)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.medication import (
    ConfirmIn,
    ConfirmOut,
    ConfirmRequestIn,
    ConfirmRequestOut,
    DoseListOut,
    DoseOut,
    EscalateOut,
    ExtendIn,
    DoseStatus,
    MedicationIn,
    MedicationListOut,
    MedicationOut,
    MedicationUpdate,
)
from app.services import medication_service

router = APIRouter(tags=["Medication"])


@router.post("/dependents/{dependent_id}/medications", response_model=MedicationListOut, status_code=201)
def create_medication(
    dependent_id: uuid.UUID, body: MedicationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """One schedule row is created per time in `times`."""
    return medication_service.create(db, user, dependent_id, body)


@router.get("/dependents/{dependent_id}/medications", response_model=MedicationListOut)
def list_medications(
    dependent_id: uuid.UUID,
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return medication_service.list_schedules(db, user, dependent_id, include_inactive)


@router.put("/dependents/{dependent_id}/medications/{schedule_id}", response_model=MedicationOut)
def update_medication(
    dependent_id: uuid.UUID,
    schedule_id: uuid.UUID,
    body: MedicationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return medication_service.update_schedule(db, user, dependent_id, schedule_id, body)


@router.delete("/dependents/{dependent_id}/medications/{schedule_id}", status_code=204)
def delete_medication(
    dependent_id: uuid.UUID, schedule_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    medication_service.deactivate(db, user, dependent_id, schedule_id)
    return Response(status_code=204)


@router.get("/dependents/{dependent_id}/medication-doses", response_model=DoseListOut)
def list_doses(
    dependent_id: uuid.UUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    status: DoseStatus | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Default range: 24 hours back to 24 hours ahead."""
    return medication_service.list_doses(db, user, dependent_id, from_, to, status)


@router.post("/dependents/{dependent_id}/medication-doses/{confirmation_id}/extend", response_model=DoseOut)
def extend_dose(
    dependent_id: uuid.UUID,
    confirmation_id: uuid.UUID,
    body: ExtendIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """FR-D1 option 1 (Guardian): give more time. A missed dose goes back to pending and its alert closes."""
    return medication_service.extend(db, user, dependent_id, confirmation_id, (body or ExtendIn()).minutes)


@router.post("/dependents/{dependent_id}/medication-doses/{confirmation_id}/escalate", response_model=EscalateOut)
def escalate_dose(
    dependent_id: uuid.UUID, confirmation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """FR-D1 option 2 (Guardian): move the missed-dose alert up to the Secondary Guardians now."""
    return medication_service.escalate(db, user, dependent_id, confirmation_id)


@router.post("/medications/{schedule_id}/confirm-request", response_model=ConfirmRequestOut)
def confirm_request(
    schedule_id: uuid.UUID,
    body: ConfirmRequestIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 1 (Dependent only): returns a short-lived token for the dose that is due."""
    return medication_service.confirm_request(
        db, user, user.user_id, schedule_id, body.confirmation_id if body else None
    )


@router.post("/medications/{schedule_id}/confirm", response_model=ConfirmOut)
def confirm(
    schedule_id: uuid.UUID, body: ConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Step 2 (Dependent only): send the token from step 1 to mark the dose as taken."""
    return medication_service.confirm(db, user, user.user_id, schedule_id, body.confirm_token)
