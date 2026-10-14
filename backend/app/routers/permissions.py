"""
Permission dashboard router (Task 1.6, FR-A4).

SDS 11.1:  PUT /dependents/{id}/permissions/{module}
Added:     GET /dependents/{id}/permissions      (Primary's dashboard: every Secondary x module)
           GET /dependents/{id}/permissions/me   (what I may do for this Dependent)
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_verified_guardian
from app.models import User
from app.schemas.permissions import DashboardOut, MyPermissionsOut, PermissionOut, SetPermissionRequest
from app.services import permission_service

router = APIRouter(prefix="/dependents", tags=["Permissions"])


@router.get("/{dependent_id}/permissions", response_model=DashboardOut)
def permission_dashboard(
    dependent_id: uuid.UUID, user: User = Depends(require_verified_guardian), db: Session = Depends(get_db)
):
    """Primary only: every Secondary Guardian and which modules they may use."""
    return permission_service.dashboard(db, user, dependent_id)


@router.get("/{dependent_id}/permissions/me", response_model=MyPermissionsOut)
def my_permissions(dependent_id: uuid.UUID, user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)):
    """Any linked Guardian: my own effective access for this Dependent."""
    return permission_service.my_permissions(db, user, dependent_id)


@router.put("/{dependent_id}/permissions/{module}", response_model=PermissionOut)
def set_permission(
    dependent_id: uuid.UUID,
    module: str,
    body: SetPermissionRequest,
    user: User = Depends(require_verified_guardian),
    db: Session = Depends(get_db),
):
    """Primary only: grant or revoke one module for one Secondary Guardian."""
    return permission_service.set_permission(db, user, dependent_id, module, body.guardian_id, body.granted)
