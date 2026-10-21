"""
Location router (Task 2.1, FR-C1 / FR-C4).

SDS 11.1:  GET  /dependents/{id}/location        latest position (JWT + permission check)
Added:     POST /dependents/{id}/location        the Dependent's phone sends a fix (SDS has no ingest endpoint)
           GET  /dependents/{id}/location/history   past positions (FR-C4)
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_module_access, require_role
from app.models import User
from app.schemas.location import LatestLocationOut, LocationAck, LocationHistoryOut, LocationUpdateRequest
from app.services import location_service

router = APIRouter(prefix="/dependents", tags=["Location"])


@router.post("/{dependent_id}/location", response_model=LocationAck)
def send_location(
    dependent_id: uuid.UUID,
    body: LocationUpdateRequest,
    user: User = Depends(require_role("dependent")),
    db: Session = Depends(get_db),
):
    """Dependent device only. Stores the fix and tells the phone how long to wait before the next one."""
    return location_service.ingest(db, user, dependent_id, body)


@router.get("/{dependent_id}/location", response_model=LatestLocationOut)
def latest_location(
    dependent_id: uuid.UUID,
    user: User = Depends(require_module_access("live_location")),
    db: Session = Depends(get_db),
):
    """Primary always; a Secondary only while 'live_location' is granted."""
    return location_service.latest(db, dependent_id)


@router.get("/{dependent_id}/location/history", response_model=LocationHistoryOut)
def location_history(
    dependent_id: uuid.UUID,
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_module_access("live_location")),
    db: Session = Depends(get_db),
):
    """Newest first. Same permission as the live location."""
    return location_service.history(db, dependent_id, start, end, limit)
