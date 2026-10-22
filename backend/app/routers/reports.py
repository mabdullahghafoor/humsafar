"""
Summary reports router (Task 7.2, FR-Q2). Guardians only.

PUT    /dependents/{id}/reports/schedule        switch the weekly / monthly report on (or change it)
GET    /dependents/{id}/reports/schedule        what is switched on (frequency null = off)
DELETE /dependents/{id}/reports/schedule        switch it off
POST   /dependents/{id}/reports                 make a report now for the last 7 to 90 days
GET    /dependents/{id}/reports                 my reports for this Dependent, newest first
GET    /dependents/{id}/reports/{report_id}/download   the PDF
DELETE /dependents/{id}/reports/{report_id}     delete one
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.reports import ReportCreateIn, ReportList, ReportOut, ScheduleIn, ScheduleOut
from app.services import report_service as svc

router = APIRouter(tags=["Summary reports"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


@router.put("/dependents/{dependent_id}/reports/schedule", response_model=ScheduleOut)
def put_schedule(dependent_id: uuid.UUID, body: ScheduleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.set_schedule(db, user, dependent_id, body.frequency)


@router.get("/dependents/{dependent_id}/reports/schedule", response_model=ScheduleOut)
def get_schedule(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_schedule(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/reports/schedule", status_code=204)
def delete_schedule(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.clear_schedule(db, user, dependent_id)
    return Response(status_code=204)


@router.post("/dependents/{dependent_id}/reports", response_model=ReportOut, status_code=201)
def create_report(dependent_id: uuid.UUID, body: ReportCreateIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.create(db, user, dependent_id, (body or ReportCreateIn()).days)


@router.get("/dependents/{dependent_id}/reports", response_model=ReportList)
def list_reports(
    dependent_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_reports(db, user, dependent_id, limit, offset)


@router.get("/dependents/{dependent_id}/reports/{report_id}/download")
def download_report(dependent_id: uuid.UUID, report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pdf, name = svc.download(db, user, dependent_id, report_id)
    return Response(pdf, media_type="application/pdf", headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{name}"'})


@router.delete("/dependents/{dependent_id}/reports/{report_id}", status_code=204)
def delete_report(dependent_id: uuid.UUID, report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete_report(db, user, dependent_id, report_id)
    return Response(status_code=204)
