"""
Audit log router (Task 6.6, FR-N3).

GET /dependents/{id}/audit-log   who did what for this Dependent (Primary Guardian only), newest first
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.audit import AuditList
from app.services import audit_service as svc

router = APIRouter(tags=["Audit log"])


@router.get("/dependents/{dependent_id}/audit-log", response_model=AuditList)
def audit_log(
    dependent_id: uuid.UUID,
    action: str | None = Query(None, max_length=60, description="Only this action, e.g. camera_view_started"),
    actor_id: uuid.UUID | None = Query(None, description="Only actions by this person"),
    since: datetime | None = Query(None, description="From this time (inclusive)"),
    until: datetime | None = Query(None, description="Until this time (exclusive)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_entries(db, user, dependent_id, action=action, actor_id=actor_id, since=since, until=until, limit=limit, offset=offset)
