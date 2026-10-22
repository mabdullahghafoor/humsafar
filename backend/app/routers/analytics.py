"""
Analytics router (Task 7.1, FR-Q1). Read only; Guardians only.

GET /dependents/{id}/analytics/adherence   medication adherence trend (needs medication_management)
GET /dependents/{id}/analytics/vitals      vitals trends (needs health_records)
GET /dependents/{id}/analytics             both in one call (a part without permission is null)
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.analytics import AdherenceReport, AnalyticsOverview, VitalsReport
from app.services import analytics_service as svc

router = APIRouter(tags=["Analytics"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
DAYS = Query(30, ge=1, le=90, description="How many days to look back, today included (1 to 90).")


@router.get("/dependents/{dependent_id}/analytics/adherence", response_model=AdherenceReport)
def adherence(dependent_id: uuid.UUID, response: Response, days: int = DAYS, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.adherence(db, user, dependent_id, days)


@router.get("/dependents/{dependent_id}/analytics/vitals", response_model=VitalsReport)
def vitals(
    dependent_id: uuid.UUID,
    response: Response,
    days: int = DAYS,
    metric_type: str | None = Query(None, description="Only this metric: blood_pressure, blood_sugar, spo2, temperature or heart_rate"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers.update(NO_STORE)
    return svc.vitals(db, user, dependent_id, days, metric_type)


@router.get("/dependents/{dependent_id}/analytics", response_model=AnalyticsOverview)
def overview(dependent_id: uuid.UUID, response: Response, days: int = DAYS, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    return svc.overview(db, user, dependent_id, days)
