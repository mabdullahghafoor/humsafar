"""
Medical Vault router (Task 5.1, FR-G1 and FR-G3).

POST   /dependents/{id}/records                       add a record (file and / or note; multipart form)
GET    /dependents/{id}/records                       list (filter by category / year / month; paged)
GET    /dependents/{id}/records/export                PDF export: complete, year or month
POST   /dependents/{id}/records/share                 make a read-only doctor link (default 72 h)
GET    /dependents/{id}/records/share                 list the links
DELETE /dependents/{id}/records/share/{share_id}      cancel a link
GET    /dependents/{id}/records/{record_id}           one record
GET    /dependents/{id}/records/{record_id}/file      download the file (decrypted)
PATCH  /dependents/{id}/records/{record_id}           change title / category / date / note
DELETE /dependents/{id}/records/{record_id}           delete a record and its file
GET    /shared/records/{token}                        the doctor's link: the PDF, no login
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.models import User
from app.schemas.records import Category, RecordList, RecordOut, RecordUpdate, Scope, ShareCreated, ShareIn, ShareList, ShareOut, check_period
from app.services import records_service as svc

router = APIRouter(tags=["Medical Vault"])
public_router = APIRouter(tags=["Medical Vault"])

NO_STORE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


@router.post("/dependents/{dependent_id}/records", response_model=RecordOut, status_code=201)
async def add_record(
    dependent_id: uuid.UUID,
    response: Response,
    category: Category = Form(...),
    title: str = Form(..., min_length=1, max_length=150),
    record_date: date = Form(..., description="The date of the document or visit."),
    notes: str | None = Form(None, max_length=5000),
    client_id: uuid.UUID | None = Form(None, description="Optional random id: a retry with the same id saves nothing twice."),
    file: UploadFile | None = File(None, description="PDF, JPEG or PNG, up to 10 MB. Leave out for a note-only record."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = b""
    if file is not None:
        data = await file.read(get_settings().RECORD_MAX_BYTES + 1)  # never read more than the limit + 1 byte
    out = await run_in_threadpool(
        svc.create, db, user, dependent_id, category=category, title=title, record_date=record_date, notes=notes,
        client_id=client_id, upload_name=file.filename if file is not None else None, data=data,
    )
    if out.already_saved:
        response.status_code = 200
    return out


@router.get("/dependents/{dependent_id}/records", response_model=RecordList)
def list_records(
    dependent_id: uuid.UUID,
    category: Category | None = None,
    year: int | None = Query(None, ge=1900, le=2200),
    month: int | None = Query(None, ge=1, le=12),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_records(db, user, dependent_id, category=category, year=year, month=month, limit=limit, offset=offset)


@router.get("/dependents/{dependent_id}/records/export")
def export_records(
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


@router.post("/dependents/{dependent_id}/records/share", response_model=ShareCreated, status_code=201)
def create_share(dependent_id: uuid.UUID, body: ShareIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.create_share(db, user, dependent_id, body)


@router.get("/dependents/{dependent_id}/records/share", response_model=ShareList)
def list_shares(dependent_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.list_shares(db, user, dependent_id)


@router.delete("/dependents/{dependent_id}/records/share/{share_id}", response_model=ShareOut)
def revoke_share(dependent_id: uuid.UUID, share_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.revoke_share(db, user, dependent_id, share_id)


@router.get("/dependents/{dependent_id}/records/{record_id}", response_model=RecordOut)
def get_record(dependent_id: uuid.UUID, record_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_one(db, user, dependent_id, record_id)


@router.get("/dependents/{dependent_id}/records/{record_id}/file")
def download_file(dependent_id: uuid.UUID, record_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data, ctype, name = svc.get_file(db, user, dependent_id, record_id)
    return Response(data, media_type=ctype, headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{name}"'})


@router.patch("/dependents/{dependent_id}/records/{record_id}", response_model=RecordOut)
def change_record(
    dependent_id: uuid.UUID, record_id: uuid.UUID, body: RecordUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return svc.update_record(db, user, dependent_id, record_id, body)


@router.delete("/dependents/{dependent_id}/records/{record_id}", status_code=204)
def delete_record(dependent_id: uuid.UUID, record_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete_record(db, user, dependent_id, record_id)
    return Response(status_code=204)


@public_router.get("/shared/records/{token}")
def open_shared(token: str, db: Session = Depends(get_db)):
    """The link a doctor opens. No login: the secret in the address is the key. It answers with the PDF."""
    if not 20 <= len(token) <= 100:
        raise AppError(404, "SHARE_NOT_FOUND", "This link does not exist.")
    pdf, name = svc.open_share(db, token)
    return Response(
        pdf, media_type="application/pdf",
        headers={**NO_STORE, "X-Robots-Tag": "noindex", "Content-Disposition": f'inline; filename="{name}"'},
    )
