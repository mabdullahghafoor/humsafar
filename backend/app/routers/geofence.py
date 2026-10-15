"""
Geofence router (Task 2.2, FR-C2 / FR-C3).

SDS 11.1:  POST /dependents/{id}/geofences                 create a zone (Primary only)
Added:     GET /dependents/{id}/geofences                  list zones (Primary, or Secondary with live_location)
           PUT /dependents/{id}/geofences/{geofence_id}    change a zone (Primary only)
           DELETE /dependents/{id}/geofences/{geofence_id} remove a zone (Primary only)
           GET /dependents/{id}/geofence-status            inside / outside + open breach
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_module_access, require_verified_guardian
from app.models import User
from app.schemas.geofence import GeofenceIn, GeofenceListOut, GeofenceOut, GeofenceStatusOut
from app.services import geofence_service

router = APIRouter(prefix="/dependents", tags=["Geofences"])


@router.post("/{dependent_id}/geofences", response_model=GeofenceOut, status_code=201)
def create_geofence(
    dependent_id: uuid.UUID, body: GeofenceIn, user: User = Depends(require_verified_guardian), db: Session = Depends(get_db)
):
    """Primary only. Up to 10 zones per Dependent; being inside any one of them is safe."""
    return geofence_service.create(db, user, dependent_id, body)


@router.get("/{dependent_id}/geofences", response_model=GeofenceListOut)
def list_geofences(
    dependent_id: uuid.UUID, user: User = Depends(require_module_access("live_location")), db: Session = Depends(get_db)
):
    return geofence_service.list_zones(db, dependent_id)


@router.put("/{dependent_id}/geofences/{geofence_id}", response_model=GeofenceOut)
def update_geofence(
    dependent_id: uuid.UUID,
    geofence_id: uuid.UUID,
    body: GeofenceIn,
    user: User = Depends(require_verified_guardian),
    db: Session = Depends(get_db),
):
    return geofence_service.update(db, user, dependent_id, geofence_id, body)


@router.delete("/{dependent_id}/geofences/{geofence_id}", status_code=204)
def delete_geofence(
    dependent_id: uuid.UUID,
    geofence_id: uuid.UUID,
    user: User = Depends(require_verified_guardian),
    db: Session = Depends(get_db),
):
    geofence_service.delete(db, user, dependent_id, geofence_id)
    return Response(status_code=204)


@router.get("/{dependent_id}/geofence-status", response_model=GeofenceStatusOut)
def geofence_status(
    dependent_id: uuid.UUID, user: User = Depends(require_module_access("live_location")), db: Session = Depends(get_db)
):
    """Where the Dependent is relative to the zones, based on their newest fix."""
    return geofence_service.status(db, dependent_id)
