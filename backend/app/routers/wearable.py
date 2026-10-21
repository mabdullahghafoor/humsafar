"""
Wearable band router (Task 5.4, FR-H2). Mock data first; the real band is Task 5.5.

POST   /dependents/{id}/wearable         pair the band (Dependent or Primary)
GET    /dependents/{id}/wearable         band status: not_paired / waiting_for_first_data / receiving / no_data
DELETE /dependents/{id}/wearable         unpair (readings are kept)
POST   /dependents/{id}/wearable/sync    the Dependent's phone sends a batch of band readings
POST   /dependents/{id}/wearable/mock    demo: make fake heart-rate readings (switch: WEARABLE_MOCK_ENABLED)
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.wearable import BandOut, BandPairIn, BandStatus, MockIn, SyncIn, SyncOut
from app.services import wearable_service as svc

router = APIRouter(tags=["Wearable band"])


@router.post("/dependents/{dependent_id}/wearable", response_model=BandOut, status_code=201)
def pair_band(dependent_id: uuid.UUID, body: BandPairIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    band, created = svc.pair(db, user, dependent_id, body)
    if not created:
        response.status_code = 200
    return band


@router.get("/dependents/{dependent_id}/wearable", response_model=BandStatus)
def band_status(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.status(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/wearable", status_code=204)
def unpair_band(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.unpair(db, user, dependent_id)
    return Response(status_code=204)


@router.post("/dependents/{dependent_id}/wearable/sync", response_model=SyncOut)
def sync_band(dependent_id: uuid.UUID, body: SyncIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.sync(db, user, dependent_id, body)


@router.post("/dependents/{dependent_id}/wearable/mock", response_model=SyncOut)
def mock_band(dependent_id: uuid.UUID, body: MockIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.mock(db, user, dependent_id, body or MockIn())
