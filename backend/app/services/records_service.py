"""
Medical Vault (Task 5.1, FR-G1 and FR-G3): records, PDF export, doctor-shareable links.

Who may do what
- The Dependent: their own records (add, read, export, make links). Edit / delete only what they added.
- A Guardian: the Primary always; a Secondary needs the `health_records` permission (FR-A4). Same check for
  every endpoint here, so removing the permission takes effect on the next request.
- Edit / delete: the person who added the record, or the Primary Guardian.
- `visible_categories` is the single place that says which record categories a person may see. Today it
  returns all four for the Primary and the Dependent and, for a Secondary, all except the categories the Primary
  hid (Task 5.2, FR-G2, see record_access_service). Every read, download, export and link below goes through it.

Files are PDF / JPEG / PNG (checked by their first bytes), at most RECORD_MAX_BYTES, stored encrypted (FR-N2).
"""

import calendar
import hashlib
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, DependentProfile, MedicalRecord, RecordShare, User
from app.models.medical import RECORD_CATEGORIES
from app.schemas.records import RecordList, RecordOut, RecordUpdate, ShareCreated, ShareIn, ShareList, ShareOut
from app.services import crypto_service, linkage_service, permission_service, record_access_service, records_pdf, storage_service, vitals_service

MODULE = "health_records"
EARLIEST = date(1900, 1, 1)


# ------------------------------------------------------------------ access

def authorize(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    """The Dependent for their own records; a Guardian needs `health_records` (Primary always)."""
    if user.role == "dependent":
        if user.user_id != dependent_id:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return
    permission_service.check_module_access(db, user, dependent_id, MODULE)


def visible_categories(db: Session, user: User, dependent_id: uuid.UUID) -> tuple[str, ...]:
    """The record categories this person may see (Task 5.2, FR-G2): all of them, minus what the Primary hid from a Secondary."""
    return record_access_service.visible_for(db, user, dependent_id)


def _audit(db: Session, user_id: uuid.UUID, action: str, target_type: str, target_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=user_id, action=action, target_type=target_type, target_id=target_id))


def _is_primary(db: Session, user: User, dependent_id: uuid.UUID) -> bool:
    return user.role == "guardian" and linkage_service._is_primary_of(db, user.user_id, dependent_id)


# ------------------------------------------------------------------ files

def _sniff(data: bytes) -> str | None:
    """(content type) from the first bytes, never from the name the app sent."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


_EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}


def _clean_name(upload_name: str | None, content_type: str) -> str:
    stem = re.split(r"[\\/]", upload_name or "")[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    stem = re.sub(r"[^\w .\-()]", "", stem, flags=re.ASCII).strip(" .-")[:100]
    return (stem or "record") + _EXT[content_type]


def _read_file(rec: MedicalRecord) -> bytes:
    path = storage_service.get_storage("records").path(rec.file_url)
    if path is None:
        raise AppError(404, "FILE_NOT_FOUND", "The file of this record is no longer available.")
    try:
        return crypto_service.decrypt(path.read_bytes())
    except crypto_service.DecryptError:
        raise AppError(500, "FILE_UNREADABLE", "The stored file is damaged and cannot be opened.")


# ------------------------------------------------------------------ output

def _name_map(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    return {u.user_id: (u.full_name or "").strip() or None for u in db.scalars(select(User).where(User.user_id.in_(ids)))}


def _outs(db: Session, recs: list[MedicalRecord], user: User, dependent_id: uuid.UUID, *, already: bool = False) -> list[RecordOut]:
    primary = _is_primary(db, user, dependent_id)
    names = _name_map(db, {r.uploaded_by for r in recs})
    return [
        RecordOut(
            record_id=r.record_id, dependent_id=r.dependent_id, category=r.type, title=r.title, notes=r.notes,
            record_date=r.record_date, has_file=r.file_url is not None, file_name=r.file_name, content_type=r.content_type,
            size_bytes=r.size_bytes,
            file_path=f"/dependents/{r.dependent_id}/records/{r.record_id}/file" if r.file_url else None,
            uploaded_by=r.uploaded_by, uploaded_by_name=names.get(r.uploaded_by), uploaded_at=r.uploaded_at,
            can_modify=primary or r.uploaded_by == user.user_id, already_saved=already,
        )
        for r in recs
    ]


# ------------------------------------------------------------------ period filter

def period_conditions(year: int | None, month: int | None) -> list:
    if year is None:
        return []
    if month is None:
        return [MedicalRecord.record_date >= date(year, 1, 1), MedicalRecord.record_date < date(year + 1, 1, 1)]
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return [MedicalRecord.record_date >= start, MedicalRecord.record_date < end]


# ------------------------------------------------------------------ create / read / update / delete

def _text(value: str | None, field: str) -> str | None:
    """Trimmed text. A NUL character cannot be stored in the database, so it is refused as bad input."""
    if value is None:
        return None
    if "\x00" in value:
        raise AppError(422, "VALIDATION_ERROR", f"{field} contains a character that is not allowed.")
    return value.strip()


def _check_date(d: date) -> None:
    if d < EARLIEST or d > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise AppError(422, "INVALID_DATE", "The record date cannot be before 1900 or in the future.")


def _same(old: MedicalRecord, dependent_id, category, title, notes, record_date, size, ctype) -> bool:
    return (old.dependent_id == dependent_id and old.type == category and old.title == title and old.notes == notes
            and old.record_date == record_date and old.size_bytes == size and old.content_type == ctype)


def create(
    db: Session, user: User, dependent_id: uuid.UUID, *, category: str, title: str, record_date: date,
    notes: str | None, client_id: uuid.UUID | None, upload_name: str | None, data: bytes,
) -> RecordOut:
    s = get_settings()
    authorize(db, user, dependent_id)
    if category not in visible_categories(db, user, dependent_id):
        raise AppError(403, "CATEGORY_NOT_ALLOWED", "You may not use this record category.", {"category": category})
    title = _text(title or "", "The title")
    if not title:
        raise AppError(422, "VALIDATION_ERROR", "The title is empty.")
    notes = _text(notes, "The note") or None
    _check_date(record_date)
    ctype = None
    if data:
        if len(data) > s.RECORD_MAX_BYTES:
            raise AppError(413, "FILE_TOO_LARGE", f"The file is too big (limit {s.RECORD_MAX_BYTES // 1_000_000} MB).")
        ctype = _sniff(data)
        if ctype is None:
            raise AppError(415, "UNSUPPORTED_FILE", "Only PDF, JPEG and PNG files are accepted.")
    elif notes is None:
        raise AppError(422, "RECORD_NEEDS_CONTENT", "Add a file, a note, or both.")
    size = len(data) if data else None

    def repeat() -> RecordOut | None:
        if client_id is None:
            return None
        old = db.scalar(select(MedicalRecord).where(MedicalRecord.uploaded_by == user.user_id, MedicalRecord.client_id == client_id))
        if old is None:
            return None
        if not _same(old, dependent_id, category, title, notes, record_date, size, ctype):
            raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different record.")
        return _outs(db, [old], user, dependent_id, already=True)[0]

    if (again := repeat()) is not None:
        return again
    store = storage_service.get_storage("records")
    key = store.save(crypto_service.encrypt(data), ".bin") if data else None
    try:
        linkage_service._lock_dependent(db, dependent_id)  # one upload at a time per Dependent: the cap cannot be beaten
        if (again := repeat()) is not None:  # an identical retry that finished while we waited for the lock
            db.rollback()
            if key:
                store.delete(key)
            return again
        count = db.scalar(select(func.count()).select_from(MedicalRecord).where(MedicalRecord.dependent_id == dependent_id))
        if count >= s.RECORDS_MAX_PER_DEPENDENT:
            raise AppError(409, "RECORDS_LIMIT", f"This vault already holds {s.RECORDS_MAX_PER_DEPENDENT} records.")
        rec = MedicalRecord(
            dependent_id=dependent_id, type=category, title=title, notes=notes, record_date=record_date, file_url=key,
            file_name=_clean_name(upload_name, ctype) if ctype else None, content_type=ctype, size_bytes=size,
            uploaded_by=user.user_id, client_id=client_id,
        )
        db.add(rec)
        db.flush()
        _audit(db, user.user_id, "record_added", "medical_record", rec.record_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        if key:
            store.delete(key)
        raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different record.")
    except BaseException:
        db.rollback()
        if key:
            store.delete(key)
        raise
    db.refresh(rec)
    return _outs(db, [rec], user, dependent_id)[0]


def list_records(
    db: Session, user: User, dependent_id: uuid.UUID, *, category: str | None, year: int | None, month: int | None,
    limit: int, offset: int,
) -> RecordList:
    authorize(db, user, dependent_id)
    if month is not None and year is None:
        raise AppError(422, "VALIDATION_ERROR", "Send `year` together with `month`.")
    allowed = visible_categories(db, user, dependent_id)
    if category is not None and category not in RECORD_CATEGORIES:
        raise AppError(422, "VALIDATION_ERROR", "Unknown category.", {"allowed": list(RECORD_CATEGORIES)})
    where = [MedicalRecord.dependent_id == dependent_id, MedicalRecord.type.in_(allowed), *period_conditions(year, month)]
    if category is not None:
        where.append(MedicalRecord.type == category)
    total = db.scalar(select(func.count()).select_from(MedicalRecord).where(*where))
    rows = list(db.scalars(
        select(MedicalRecord).where(*where)
        .order_by(MedicalRecord.record_date.desc(), MedicalRecord.uploaded_at.desc(), MedicalRecord.record_id.desc())
        .limit(limit).offset(offset)
    ))
    return RecordList(items=_outs(db, rows, user, dependent_id), total=total, limit=limit, offset=offset)


def _get(db: Session, user: User, dependent_id: uuid.UUID, record_id: uuid.UUID, *, lock: bool = False) -> MedicalRecord:
    authorize(db, user, dependent_id)
    q = select(MedicalRecord).where(MedicalRecord.record_id == record_id, MedicalRecord.dependent_id == dependent_id)
    rec = db.scalar(q.with_for_update() if lock else q)
    if rec is None or rec.type not in visible_categories(db, user, dependent_id):
        raise AppError(404, "RECORD_NOT_FOUND", "Record not found.")  # a hidden category looks the same as a missing record
    return rec


def get_one(db: Session, user: User, dependent_id: uuid.UUID, record_id: uuid.UUID) -> RecordOut:
    return _outs(db, [_get(db, user, dependent_id, record_id)], user, dependent_id)[0]


def get_file(db: Session, user: User, dependent_id: uuid.UUID, record_id: uuid.UUID) -> tuple[bytes, str, str]:
    """(decrypted bytes, content type, file name). Every download is written to the audit log (FR-N3)."""
    rec = _get(db, user, dependent_id, record_id)
    if rec.file_url is None:
        raise AppError(404, "NO_FILE", "This record has no file.")
    data = _read_file(rec)
    _audit(db, user.user_id, "record_downloaded", "medical_record", rec.record_id)
    db.commit()
    return data, rec.content_type, rec.file_name or "record"


def _require_modify(db: Session, user: User, dependent_id: uuid.UUID, rec: MedicalRecord) -> None:
    if rec.uploaded_by != user.user_id and not _is_primary(db, user, dependent_id):
        raise AppError(403, "RECORD_MODIFY_DENIED", "Only the person who added this record, or the Primary Guardian, can change it.")


def update_record(db: Session, user: User, dependent_id: uuid.UUID, record_id: uuid.UUID, body: RecordUpdate) -> RecordOut:
    rec = _get(db, user, dependent_id, record_id, lock=True)
    _require_modify(db, user, dependent_id, rec)
    fields = body.model_fields_set
    if "category" in fields:
        if body.category not in visible_categories(db, user, dependent_id):
            raise AppError(403, "CATEGORY_NOT_ALLOWED", "You may not use this record category.", {"category": body.category})
        rec.type = body.category
    if "title" in fields:
        title = _text(body.title, "The title")
        if not title:
            raise AppError(422, "VALIDATION_ERROR", "The title is empty.")
        rec.title = title
    if "record_date" in fields:
        _check_date(body.record_date)
        rec.record_date = body.record_date
    if "notes" in fields:
        rec.notes = _text(body.notes, "The note") or None
    if rec.file_url is None and rec.notes is None:
        db.rollback()
        raise AppError(422, "RECORD_NEEDS_CONTENT", "A record without a file needs a note.")
    _audit(db, user.user_id, "record_changed", "medical_record", rec.record_id)
    db.commit()
    db.refresh(rec)
    return _outs(db, [rec], user, dependent_id)[0]


def delete_record(db: Session, user: User, dependent_id: uuid.UUID, record_id: uuid.UUID) -> None:
    rec = _get(db, user, dependent_id, record_id, lock=True)
    _require_modify(db, user, dependent_id, rec)
    key = rec.file_url
    db.delete(rec)
    _audit(db, user.user_id, "record_deleted", "medical_record", record_id)
    db.commit()
    if key:  # after the commit: if the commit failed, the file is still there
        storage_service.get_storage("records").delete(key)


# ------------------------------------------------------------------ export

def _export_bytes(
    db: Session, dependent_id: uuid.UUID, scope: str, year: int | None, month: int | None, categories: tuple[str, ...] | list[str],
    include_vitals: bool = False,
) -> bytes:
    s = get_settings()
    where = [MedicalRecord.dependent_id == dependent_id, MedicalRecord.type.in_(list(categories)), *period_conditions(year, month)]
    total = db.scalar(select(func.count()).select_from(MedicalRecord).where(*where))
    recs = list(db.scalars(
        select(MedicalRecord).where(*where)
        .order_by(MedicalRecord.record_date.desc(), MedicalRecord.uploaded_at.desc(), MedicalRecord.record_id.desc())
        .limit(s.EXPORT_MAX_RECORDS)
    ))
    names = _name_map(db, {r.uploaded_by for r in recs} | {dependent_id})
    budget = s.EXPORT_MAX_BYTES
    rows = []
    for r in recs:
        data, skipped = None, None
        if r.file_url:
            if (r.size_bytes or 0) > budget:
                skipped = "too large for this export; download it from the app"
            else:
                try:
                    data = _read_file(r)
                    budget -= len(data)
                except AppError:
                    skipped = "the file is no longer available"
        rows.append({
            "date": r.record_date, "category": r.type, "title": r.title, "notes": r.notes,
            "added_by": names.get(r.uploaded_by) or "A Guardian", "added_at": r.uploaded_at,
            "content_type": r.content_type, "name": r.file_name or "file", "data": data, "skipped": skipped,
        })
    v_rows, v_total = vitals_service.export_rows(db, dependent_id, year, month) if include_vitals else (None, 0)
    return records_pdf.build(
        person_name=names.get(dependent_id) or "Dependent", scope=scope, year=year, month=month, rows=rows, total_matching=total,
        vitals=v_rows, vitals_total=v_total,
    )


def export_pdf(
    db: Session, user: User, dependent_id: uuid.UUID, scope: str, year: int | None, month: int | None, include_vitals: bool = False
) -> tuple[bytes, str]:
    authorize(db, user, dependent_id)
    pdf = _export_bytes(db, dependent_id, scope, year, month, visible_categories(db, user, dependent_id), include_vitals)
    _audit(db, user.user_id, "records_exported", "dependent", dependent_id)
    db.commit()
    return pdf, records_pdf.file_stem(scope, year, month) + ".pdf"


# ------------------------------------------------------------------ doctor links (FR-G3)

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _status(sh: RecordShare, now: datetime) -> str:
    if sh.revoked_at is not None:
        return "revoked"
    return "expired" if sh.expires_at <= now else "active"


def _share_out(sh: RecordShare, now: datetime) -> ShareOut:
    return ShareOut(
        share_id=sh.share_id, dependent_id=sh.dependent_id, created_by=sh.created_by, scope=sh.scope, year=sh.year,
        month=sh.month, categories=list(sh.categories), include_vitals=sh.include_vitals, created_at=sh.created_at, expires_at=sh.expires_at,
        revoked_at=sh.revoked_at, status=_status(sh, now), open_count=sh.open_count, last_opened_at=sh.last_opened_at,
    )


def create_share(db: Session, user: User, dependent_id: uuid.UUID, body: ShareIn) -> ShareCreated:
    s = get_settings()
    authorize(db, user, dependent_id)
    allowed = visible_categories(db, user, dependent_id)
    cats = list(dict.fromkeys(body.categories)) if body.categories else list(allowed)
    if any(c not in allowed for c in cats):
        raise AppError(403, "CATEGORY_NOT_ALLOWED", "You may not share a category you cannot see.")
    hours = body.hours if body.hours is not None else s.SHARE_DEFAULT_HOURS
    if hours > s.SHARE_MAX_HOURS:
        raise AppError(422, "VALIDATION_ERROR", f"A link can work for at most {s.SHARE_MAX_HOURS} hours.")
    if body.year is not None:
        today = datetime.now(timezone.utc).date()
        if body.year < 1900 or body.year > today.year + 1:
            raise AppError(422, "INVALID_DATE", "That year is not possible.")
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    linkage_service._lock_dependent(db, dependent_id)
    active = db.scalar(
        select(func.count()).select_from(RecordShare).where(
            RecordShare.dependent_id == dependent_id, RecordShare.revoked_at.is_(None), RecordShare.expires_at > now
        )
    )
    if active >= s.SHARE_MAX_ACTIVE:
        raise AppError(409, "SHARE_LIMIT", f"There are already {s.SHARE_MAX_ACTIVE} open links. Cancel one first.")
    sh = RecordShare(
        dependent_id=dependent_id, created_by=user.user_id, token_hash=_hash(token), scope=body.scope, year=body.year,
        month=body.month, categories=cats, include_vitals=body.include_vitals, created_at=now, expires_at=now + timedelta(hours=hours),
    )
    db.add(sh)
    db.flush()
    _audit(db, user.user_id, "record_share_created", "record_share", sh.share_id)
    db.commit()
    db.refresh(sh)
    path = f"/shared/records/{token}"
    base = s.PUBLIC_BASE_URL.rstrip("/")
    return ShareCreated(**_share_out(sh, now).model_dump(), token=token, url=f"{base}{path}" if base else path)


def list_shares(db: Session, user: User, dependent_id: uuid.UUID) -> ShareList:
    """The Dependent and the Primary see every link; a Secondary sees only the links they made."""
    authorize(db, user, dependent_id)
    q = select(RecordShare).where(RecordShare.dependent_id == dependent_id)
    if user.role == "guardian" and not _is_primary(db, user, dependent_id):
        q = q.where(RecordShare.created_by == user.user_id)
    now = datetime.now(timezone.utc)
    return ShareList(items=[_share_out(x, now) for x in db.scalars(q.order_by(RecordShare.created_at.desc(), RecordShare.share_id))])


def revoke_share(db: Session, user: User, dependent_id: uuid.UUID, share_id: uuid.UUID) -> ShareOut:
    authorize(db, user, dependent_id)
    sh = db.scalar(select(RecordShare).where(RecordShare.share_id == share_id, RecordShare.dependent_id == dependent_id).with_for_update())
    if sh is None:
        raise AppError(404, "SHARE_NOT_FOUND", "Link not found.")
    if sh.created_by != user.user_id and user.role != "dependent" and not _is_primary(db, user, dependent_id):
        raise AppError(403, "SHARE_MODIFY_DENIED", "Only the person who made this link, the Primary Guardian or the Dependent can cancel it.")
    now = datetime.now(timezone.utc)
    if sh.revoked_at is None:
        sh.revoked_at = now
        _audit(db, user.user_id, "record_share_revoked", "record_share", sh.share_id)
    db.commit()
    db.refresh(sh)
    return _share_out(sh, now)


def open_share(db: Session, token: str) -> tuple[bytes, str]:
    """No login: the secret token is the key. Returns (PDF, file name). Unknown token 404; cancelled or expired 410."""
    sh = db.scalar(select(RecordShare).where(RecordShare.token_hash == _hash(token)))
    if sh is None:
        raise AppError(404, "SHARE_NOT_FOUND", "This link does not exist.")
    now = datetime.now(timezone.utc)
    if sh.revoked_at is not None:
        raise AppError(410, "SHARE_REVOKED", "This link was cancelled.")
    if sh.expires_at <= now:
        raise AppError(410, "SHARE_EXPIRED", "This link has expired.")
    creator = db.get(User, sh.created_by)
    if creator is not None and creator.role == "guardian":
        try:  # a Secondary who lost access also loses the links they made
            permission_service.check_module_access(db, creator, sh.dependent_id, MODULE)
        except AppError:
            raise AppError(410, "SHARE_REVOKED", "This link was cancelled.")
    cats = list(sh.categories)
    if creator is not None and creator.role == "guardian":
        # FR-G2: a category hidden from the Secondary after they made the link disappears from the link too
        vis = visible_categories(db, creator, sh.dependent_id)
        cats = [c for c in cats if c in vis]
        if not cats:
            raise AppError(410, "SHARE_REVOKED", "This link was cancelled.")
    if db.get(DependentProfile, sh.dependent_id) is None:
        raise AppError(404, "SHARE_NOT_FOUND", "This link does not exist.")
    got = db.execute(
        update(RecordShare)
        .where(RecordShare.share_id == sh.share_id, RecordShare.revoked_at.is_(None), RecordShare.expires_at > now)
        .values(open_count=RecordShare.open_count + 1, last_opened_at=now)
        .returning(RecordShare.share_id)
    ).scalar()
    if got is None:  # cancelled or expired a moment ago
        db.rollback()
        raise AppError(410, "SHARE_REVOKED", "This link is no longer available.")
    _audit(db, sh.created_by, "record_share_opened", "record_share", sh.share_id)  # logged under the person who made the link
    db.commit()
    pdf = _export_bytes(db, sh.dependent_id, sh.scope, sh.year, sh.month, cats, sh.include_vitals)
    return pdf, records_pdf.file_stem(sh.scope, sh.year, sh.month) + ".pdf"
