"""
Manual vitals router (Task 5.3, FR-H1).

POST   /dependents/{id}/vitals                 save a reading (blood pressure, sugar, SpO2, temperature)
GET    /dependents/{id}/vitals                 list (filters metric_type, from, to; paged; newest first)
GET    /dependents/{id}/vitals/latest          the newest reading of each metric
GET    /dependents/{id}/vitals/export          a separate vitals PDF (complete / year / month)
GET    /dependents/{id}/vitals/{reading_id}    one reading
DELETE /dependents/{id}/vitals/{reading_id}    delete a reading
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.models import User
from app.schemas.records import Scope, check_period
from app.schemas.vitals import LatestVitals, VitalIn, VitalList, VitalOut
from app.services import vitals_service as svc

router = APIRouter(tags=["Vitals"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


@router.post("/dependents/{dependent_id}/vitals", response_model=VitalOut, status_code=201)
def add_vital(dependent_id: uuid.UUID, body: VitalIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = svc.create(db, user, dependent_id, body)
    if out.already_saved:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/vitals", response_model=VitalList)
def list_vitals(
    dependent_id: uuid.UUID,
    metric_type: str | None = Query(None, description="blood_pressure, blood_sugar, spo2, temperature or heart_rate"),
    from_: datetime | None = Query(None, alias="from", description="Only readings measured at or after this time (with time zone)."),
    to: datetime | None = Query(None, description="Only readings measured at or before this time (with time zone)."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_vitals(db, user, dependent_id, metric=metric_type, from_=from_, to=to, limit=limit, offset=offset)


@router.get("/dependents/{dependent_id}/vitals/latest", response_model=LatestVitals)
def latest_vitals(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.latest(db, user, dependent_id)


@router.get("/dependents/{dependent_id}/vitals/export")
def export_vitals(
    dependent_id: uuid.UUID,
    scope: Scope = "complete",
    year: int | None = Query(None, ge=1900, le=2200),
    month: int | None = Query(None, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        check_period(scope, year, month)
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc))
    pdf, name = svc.export_pdf(db, user, dependent_id, scope, year, month)
    return Response(pdf, media_type="application/pdf", headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/dependents/{dependent_id}/vitals/{reading_id}", response_model=VitalOut)
def get_vital(dependent_id: uuid.UUID, reading_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_one(db, user, dependent_id, reading_id)


@router.delete("/dependents/{dependent_id}/vitals/{reading_id}", status_code=204)
def delete_vital(dependent_id: uuid.UUID, reading_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete(db, user, dependent_id, reading_id)
    return Response(status_code=204)
