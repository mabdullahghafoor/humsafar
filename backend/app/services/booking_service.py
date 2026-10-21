"""
Home-care booking requests and the shared Activity Timeline (Task 6.2, FR-J1, FR-I2/J2).

  * A booking request is a message of intent to a directory-listed provider. Providers have no accounts (FR-J1), so the
    platform cannot ask them anything: the request is stored, shown to the family, and the app opens the dialer with
    the provider's `contact`. The status is kept by the family: pending -> confirmed -> completed, or cancelled
    (clarification 128). No payment (future scope).
  * Who: the Dependent (own), the Primary, a Secondary with `health_records` (the same gate as appointments).
    Changing a status: the person who made the request, or the Primary.
  * One open request (pending / confirmed) per Dependent and provider; at most BOOKING_MAX_OPEN open per Dependent.
  * The Activity Timeline is ONE list of every organization contact and every booking step for a Dependent, newest
    first, whoever it came from (FR-I2/J2). Entries are written in the same transaction as the action, never edited,
    and keep the organization / provider name as it was.
  * The others involved get a standard `booking_update` notification when a request is made or changes.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import ActivityLog, AuditLog, BookingRequest, GuardianDependentLink, HealthcareOrganization, HomeCareProvider, User
from app.models.directory import BOOKING_OPEN
from app.schemas.booking import ActivityList, ActivityOut, BookingIn, BookingList, BookingOut, Initiator
from app.services import linkage_service
from app.services import notification_service as ns
from app.services.records_service import authorize


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_primary(db: Session, user: User, dependent_id: uuid.UUID) -> bool:
    return user.role == "guardian" and linkage_service._is_primary_of(db, user.user_id, dependent_id)


def _audit(db: Session, user: User, action: str, target_id: uuid.UUID, dependent_id: uuid.UUID) -> None:
    db.add(AuditLog(actor_id=user.user_id, action=action, target_type="booking_request", target_id=target_id, dependent_id=dependent_id))


def _log(db: Session, dependent_id: uuid.UUID, user: User, type_: str, reference_id: uuid.UUID, subject_name: str) -> ActivityLog:
    row = ActivityLog(dependent_id=dependent_id, type=type_, reference_id=reference_id, initiated_by=user.user_id, subject_name=subject_name[:200])
    db.add(row)
    return row


def _out(db: Session, b: BookingRequest, p: HomeCareProvider, already_saved: bool = False) -> BookingOut:
    who = db.get(User, b.requested_by)
    return BookingOut(
        request_id=b.request_id, dependent_id=b.dependent_id, provider_id=p.provider_id, provider_name=p.name,
        specialization=p.specialization, contact=p.contact, service_charge=float(p.service_charge) if p.service_charge is not None else None,
        charge_unit=p.charge_unit, status=b.status, requested_by=b.requested_by, requested_by_name=(who.full_name if who else "") or "",
        requested_at=b.requested_at, preferred_at=b.preferred_at, note=b.note, updated_at=b.updated_at, already_saved=already_saved,
    )


def _tell_others(db: Session, actor: User, b: BookingRequest, provider_name: str, title: str, what: str) -> None:
    name = ns._display_name(db, b.dependent_id)
    audience = [b.dependent_id] + ns.recipients(db, b.dependent_id, ns.LINKED_PERMITTED, module="health_records")
    for uid in audience:
        if uid == actor.user_id:
            continue
        who = "Your" if uid == b.dependent_id else f"{name}'s"
        ns.notify(
            db, uid, "booking_update", ns.STANDARD, title, f"{who} home-care request to {provider_name} {what}.",
            dependent_id=b.dependent_id, extra={"request_id": str(b.request_id), "provider_name": provider_name, "status": b.status},
        )


# ------------------------------------------------------------------ bookings

def create(db: Session, user: User, dependent_id: uuid.UUID, body: BookingIn) -> BookingOut:
    S = get_settings()
    authorize(db, user, dependent_id)
    if body.client_id:
        old = db.scalar(select(BookingRequest).where(BookingRequest.requested_by == user.user_id, BookingRequest.client_id == body.client_id))
        if old is not None:
            if old.dependent_id != dependent_id or old.provider_id != body.provider_id:
                raise AppError(409, "CLIENT_ID_REUSED", "This client_id was used for a different request.")
            return _out(db, old, db.get(HomeCareProvider, old.provider_id), already_saved=True)
    now = _utcnow()
    if body.preferred_at is not None:
        if body.preferred_at <= now:
            raise AppError(422, "VALIDATION_ERROR", "preferred_at must be in the future.")
        if body.preferred_at > now + timedelta(days=S.BOOKING_MAX_AHEAD_DAYS):
            raise AppError(422, "VALIDATION_ERROR", f"preferred_at must be within {S.BOOKING_MAX_AHEAD_DAYS} days.")
    provider = db.get(HomeCareProvider, body.provider_id)
    if provider is None or not provider.is_active:
        raise AppError(404, "PROVIDER_NOT_FOUND", "Provider not found.")

    linkage_service._lock_dependent(db, dependent_id)  # serialises the open-request count for this Dependent
    open_now = db.scalar(select(func.count()).select_from(BookingRequest).where(BookingRequest.dependent_id == dependent_id, BookingRequest.status.in_(BOOKING_OPEN))) or 0
    if open_now >= S.BOOKING_MAX_OPEN:
        raise AppError(409, "TOO_MANY_OPEN_BOOKINGS", f"At most {S.BOOKING_MAX_OPEN} requests can be open at one time.")
    b = BookingRequest(dependent_id=dependent_id, provider_id=provider.provider_id, requested_by=user.user_id, preferred_at=body.preferred_at, note=body.note, client_id=body.client_id)
    db.add(b)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_booking_requests_client" in str(e.orig):
            old = db.scalar(select(BookingRequest).where(BookingRequest.requested_by == user.user_id, BookingRequest.client_id == body.client_id))
            if old is not None:
                return _out(db, old, db.get(HomeCareProvider, old.provider_id), already_saved=True)
        raise AppError(409, "BOOKING_ALREADY_OPEN", "There is already an open request to this provider for this Dependent.")
    _log(db, dependent_id, user, "booking_request", b.request_id, provider.name)
    _audit(db, user, "booking_requested", b.request_id, b.dependent_id)
    db.commit()
    db.refresh(b)
    _tell_others(db, user, b, provider.name, "New home-care request", "was made")
    return _out(db, b, provider)


def _get(db: Session, user: User, dependent_id: uuid.UUID, request_id: uuid.UUID) -> tuple[BookingRequest, HomeCareProvider]:
    authorize(db, user, dependent_id)
    b = db.get(BookingRequest, request_id)
    if b is None or b.dependent_id != dependent_id:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking request not found.")
    return b, db.get(HomeCareProvider, b.provider_id)


def get_one(db: Session, user: User, dependent_id: uuid.UUID, request_id: uuid.UUID) -> BookingOut:
    b, p = _get(db, user, dependent_id, request_id)
    return _out(db, b, p)


def list_bookings(db: Session, user: User, dependent_id: uuid.UUID, *, status: str | None, limit: int, offset: int) -> BookingList:
    authorize(db, user, dependent_id)
    where = [BookingRequest.dependent_id == dependent_id]
    if status:
        where.append(BookingRequest.status == status)
    total = db.scalar(select(func.count()).select_from(BookingRequest).where(and_(*where))) or 0
    rows = db.scalars(select(BookingRequest).where(and_(*where)).order_by(BookingRequest.requested_at.desc(), BookingRequest.request_id).limit(limit).offset(offset)).all()
    provs = {p.provider_id: p for p in db.scalars(select(HomeCareProvider).where(HomeCareProvider.provider_id.in_({r.provider_id for r in rows})))} if rows else {}
    return BookingList(items=[_out(db, r, provs[r.provider_id]) for r in rows], total=total, limit=limit, offset=offset)


# status -> (allowed from, activity type, audit action, notification title, text)
ACTIONS = {
    "confirmed": (("pending",), "booking_confirmed", "booking_confirmed", "Home-care request confirmed", "was confirmed"),
    "completed": (("confirmed",), "booking_completed", "booking_completed", "Home-care visit done", "was marked as done"),
    "cancelled": (("pending", "confirmed"), "booking_cancelled", "booking_cancelled", "Home-care request cancelled", "was cancelled"),
}


def change_status(db: Session, user: User, dependent_id: uuid.UUID, request_id: uuid.UUID, new_status: str) -> BookingOut:
    allowed_from, act_type, audit, title, what = ACTIONS[new_status]
    authorize(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    b = db.scalar(select(BookingRequest).where(BookingRequest.request_id == request_id).with_for_update())
    if b is None or b.dependent_id != dependent_id:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking request not found.")
    if b.requested_by != user.user_id and not _is_primary(db, user, dependent_id):
        raise AppError(403, "FORBIDDEN", "Only the person who made the request, or the Primary Guardian, can change it.")
    if b.status not in allowed_from:
        raise AppError(409, "BOOKING_STATUS_CONFLICT", f"A {b.status} request cannot be set to {new_status}.", {"status": b.status})
    p = db.get(HomeCareProvider, b.provider_id)
    b.status = new_status
    b.updated_at = _utcnow()
    _log(db, dependent_id, user, act_type, b.request_id, p.name)
    _audit(db, user, audit, b.request_id, b.dependent_id)
    db.commit()
    db.refresh(b)
    _tell_others(db, user, b, p.name, title, what)
    return _out(db, b, p)


# ------------------------------------------------------------------ organization contacts

def log_contact(db: Session, user: User, dependent_id: uuid.UUID, org_id: uuid.UUID) -> tuple[ActivityOut, bool]:
    """Write 'this person is contacting this organization' (the app then opens the dialer). Returns (entry, created)."""
    authorize(db, user, dependent_id)
    org = db.get(HealthcareOrganization, org_id)
    if org is None or not org.is_active:
        raise AppError(404, "NOT_FOUND", "Organization not found.")
    since = _utcnow() - timedelta(seconds=get_settings().ACTIVITY_CONTACT_DEDUPE_S)
    recent = db.scalar(
        select(ActivityLog).where(
            ActivityLog.dependent_id == dependent_id, ActivityLog.type == "org_contact", ActivityLog.initiated_by == user.user_id,
            ActivityLog.reference_id == org_id, ActivityLog.occurred_at >= since,
        ).order_by(ActivityLog.occurred_at.desc()).limit(1)
    )
    if recent is not None:
        return _activity_out(db, [recent], dependent_id)[0], False
    row = _log(db, dependent_id, user, "org_contact", org.org_id, org.name)
    db.commit()
    db.refresh(row)
    return _activity_out(db, [row], dependent_id)[0], True


# ------------------------------------------------------------------ the unified timeline

def _roles(db: Session, dependent_id: uuid.UUID, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    out = {dependent_id: "dependent"}
    links = db.scalars(select(GuardianDependentLink).where(GuardianDependentLink.dependent_id == dependent_id, GuardianDependentLink.guardian_id.in_(user_ids))).all() if user_ids else []
    for l in links:
        out[l.guardian_id] = l.role if l.status == linkage_service.ACTIVE else "former_guardian"
    return out


def _activity_out(db: Session, rows: list[ActivityLog], dependent_id: uuid.UUID) -> list[ActivityOut]:
    ids = {r.initiated_by for r in rows}
    users = {u.user_id: u for u in db.scalars(select(User).where(User.user_id.in_(ids)))} if ids else {}
    roles = _roles(db, dependent_id, ids)
    ref = {r.reference_id for r in rows if r.type.startswith("booking") and r.reference_id}
    status = {b.request_id: b.status for b in db.scalars(select(BookingRequest).where(BookingRequest.request_id.in_(ref)))} if ref else {}
    return [
        ActivityOut(
            activity_id=r.activity_id, dependent_id=r.dependent_id, type=r.type, occurred_at=r.occurred_at,
            initiated_by=Initiator(user_id=r.initiated_by, full_name=(users[r.initiated_by].full_name or "") if r.initiated_by in users else "", role=roles.get(r.initiated_by, "former_guardian")),
            subject_name=r.subject_name, reference_id=r.reference_id, booking_status=status.get(r.reference_id) if r.type.startswith("booking") else None,
        )
        for r in rows
    ]


def timeline(db: Session, user: User, dependent_id: uuid.UUID, *, type_: str | None, from_: datetime | None, to: datetime | None, limit: int, offset: int) -> ActivityList:
    authorize(db, user, dependent_id)
    where = [ActivityLog.dependent_id == dependent_id]
    if type_:
        where.append(ActivityLog.type == type_)
    if from_ is not None:
        where.append(ActivityLog.occurred_at >= from_)
    if to is not None:
        where.append(ActivityLog.occurred_at <= to)
    total = db.scalar(select(func.count()).select_from(ActivityLog).where(and_(*where))) or 0
    rows = db.scalars(select(ActivityLog).where(and_(*where)).order_by(ActivityLog.occurred_at.desc(), ActivityLog.activity_id).limit(limit).offset(offset)).all()
    return ActivityList(items=_activity_out(db, list(rows), dependent_id), total=total, limit=limit, offset=offset)
