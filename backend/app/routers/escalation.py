"""
Escalation chain router (Task 3.5, FR-D5).

GET  /dependents/{id}/escalations              alerts and where they are in the chain (Primary, or Secondary with emergency_alerts)
POST /escalations/{event_id}/acknowledge       a Guardian who was told says "I have seen it"; stops the escalation timer
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.escalation import EscalationListOut, EscalationOut, EventStatus
from app.services import escalation_service

router = APIRouter(tags=["Escalation"])


@router.get("/dependents/{dependent_id}/escalations", response_model=EscalationListOut)
def list_escalations(
    dependent_id: uuid.UUID,
    status: EventStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return escalation_service.list_events(db, user, dependent_id, status, limit)


@router.post("/escalations/{event_id}/acknowledge", response_model=EscalationOut)
def acknowledge(event_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return escalation_service.acknowledge_event(db, user, event_id)
