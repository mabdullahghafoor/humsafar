"""
Device health router (Task 2.3, FR-L1 / FR-L2).

No new endpoint for the phone: battery rides along on the location fix (POST /dependents/{id}/location).
Added: GET /dependents/{id}/device-health   battery, online/offline, last known location
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_module_access
from app.models import User
from app.schemas.device_health import DeviceHealthOut
from app.services import device_health_service

router = APIRouter(prefix="/dependents", tags=["Device health"])


@router.get("/{dependent_id}/device-health", response_model=DeviceHealthOut)
def device_health(
    dependent_id: uuid.UUID, user: User = Depends(require_module_access("live_location")), db: Session = Depends(get_db)
):
    """Primary always; a Secondary only while 'live_location' is granted."""
    return device_health_service.health(db, dependent_id)
