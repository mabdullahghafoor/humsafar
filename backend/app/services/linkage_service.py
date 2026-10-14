"""
Guardian-Dependent linkage (Task 1.5, FR-B1 / FR-B2 / FR-B4).

Rules enforced here, in code, not only by the UI:
  * Only a Primary-designated Guardian can link a new Dependent (FR-B1).
  * Exactly one Primary per Dependent: checked here AND by the database's partial
    unique index uq_one_primary_per_dependent, so a race cannot create two (FR-B2.2).
  * At most 3 Guardians per Dependent: 1 Primary + 2 Secondary (FR-B2.1). Every
    write that adds a link first locks the Dependent's row (SELECT ... FOR UPDATE),
    so two simultaneous requests cannot both slip under the cap.
  * A Guardian may be linked to many Dependents (FR-B4).
  * A Secondary account only comes from an invitation (FR-A1). The SDS has no
    invitations table, so an invitation is a signed, expiring token bound to the
    invited phone number (see security.create_invite_token).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.models import DependentProfile, GuardianDependentLink, GuardianProfile, User
from app.schemas.linkage import DependentSummary, GuardianSummary, InviteOut, LinkOut

MAX_GUARDIANS = 3  # 1 Primary + up to 2 Secondary
ACTIVE = "active"


def _link_out(link: GuardianDependentLink) -> LinkOut:
    return LinkOut(
        link_id=link.link_id,
        dependent_id=link.dependent_id,
        guardian_id=link.guardian_id,
        role=link.role,
        status=link.status,
        linked_at=link.linked_at,
    )


def _guardian_profile(db: Session, user: User) -> GuardianProfile:
    profile = db.get(GuardianProfile, user.user_id)
    if profile is None:
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    return profile


def _lock_dependent(db: Session, dependent_id: uuid.UUID) -> DependentProfile:
    """Serialise all linkage changes for one Dependent."""
    profile = db.scalar(
        select(DependentProfile).where(DependentProfile.user_id == dependent_id).with_for_update()
    )
    if profile is None:
        raise AppError(404, "DEPENDENT_NOT_FOUND", "No such Dependent.")
    return profile


def _active_links(db: Session, dependent_id: uuid.UUID) -> list[GuardianDependentLink]:
    return list(
        db.scalars(
            select(GuardianDependentLink).where(
                GuardianDependentLink.dependent_id == dependent_id,
                GuardianDependentLink.status == ACTIVE,
            )
        )
    )


def _is_primary_of(db: Session, guardian_id: uuid.UUID, dependent_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(GuardianDependentLink.link_id).where(
                GuardianDependentLink.guardian_id == guardian_id,
                GuardianDependentLink.dependent_id == dependent_id,
                GuardianDependentLink.role == "primary",
                GuardianDependentLink.status == ACTIVE,
            )
        )
        is not None
    )


def _insert_link(db: Session, guardian_id: uuid.UUID, dependent_id: uuid.UUID, role: str) -> GuardianDependentLink:
    link = GuardianDependentLink(guardian_id=guardian_id, dependent_id=dependent_id, role=role, status=ACTIVE)
    try:
        db.add(link)
        db.flush()
    except IntegrityError:
        # The database is the last line of defence against a race.
        db.rollback()
        if role == "primary":
            raise AppError(409, "PRIMARY_ALREADY_EXISTS", "This Dependent already has a Primary Guardian.")
        raise AppError(409, "ALREADY_LINKED", "You are already linked to this Dependent.")
    return link


# ----------------------------------------------------------------- primary link


def link_primary(db: Session, user: User, dependent_id: uuid.UUID) -> LinkOut:
    profile = _guardian_profile(db, user)
    if profile.guardian_role != "primary":
        raise AppError(
            403, "SECONDARY_CANNOT_LINK", "Secondary Guardians cannot link a new Dependent (FR-B1)."
        )
    _lock_dependent(db, dependent_id)
    links = _active_links(db, dependent_id)
    if any(l.guardian_id == user.user_id for l in links):
        raise AppError(409, "ALREADY_LINKED", "You are already linked to this Dependent.")
    if any(l.role == "primary" for l in links):
        raise AppError(409, "PRIMARY_ALREADY_EXISTS", "This Dependent already has a Primary Guardian.")
    if len(links) >= MAX_GUARDIANS:
        raise AppError(409, "GUARDIAN_CAP_REACHED", "This Dependent already has the maximum of 3 Guardians.")
    link = _insert_link(db, user.user_id, dependent_id, "primary")
    db.commit()
    db.refresh(link)
    return _link_out(link)


# ------------------------------------------------------------------ invitations


def create_invite(db: Session, user: User, dependent_id: uuid.UUID, invitee_phone: str) -> InviteOut:
    _guardian_profile(db, user)
    if not _is_primary_of(db, user.user_id, dependent_id):
        raise AppError(
            403, "NOT_PRIMARY_GUARDIAN", "Only this Dependent's Primary Guardian can invite Guardians."
        )
    _lock_dependent(db, dependent_id)
    links = _active_links(db, dependent_id)
    if len(links) >= MAX_GUARDIANS:
        raise AppError(409, "GUARDIAN_CAP_REACHED", "This Dependent already has the maximum of 3 Guardians.")

    # One generic answer for every reason a phone cannot be invited, so the Primary
    # cannot use this endpoint to learn who has an account (FR-A1: a Primary-designated
    # account cannot become a Secondary; Dependents are not Guardians).
    not_eligible = AppError(409, "INVITEE_NOT_ELIGIBLE", "This phone number cannot be invited.")
    existing = db.scalar(select(User).where(User.phone == invitee_phone))
    if existing is not None:
        if existing.role != "guardian":
            raise not_eligible
        existing_profile = db.get(GuardianProfile, existing.user_id)
        if existing_profile is None or existing_profile.guardian_role != "secondary":
            raise not_eligible
        if any(l.guardian_id == existing.user_id for l in links):
            raise not_eligible

    token, expires = security.create_invite_token(dependent_id, user.user_id, invitee_phone)
    db.rollback()  # release the row lock; nothing was written
    return InviteOut(
        invite_token=token,
        invited_phone=invitee_phone,
        expires_at=expires,
        expires_in=security.INVITE_VALID_DAYS * 24 * 3600,
    )


def read_invite(db: Session, token: str) -> dict:
    """Verify an invitation token. Every failure is an INVITE_* error, never a session error."""
    try:
        payload = security.decode_token(token, security.INVITE)
    except AppError as exc:
        if exc.code == "TOKEN_EXPIRED":
            raise AppError(400, "INVITE_EXPIRED", "This invitation has expired. Ask for a new one.")
        raise AppError(400, "INVITE_INVALID", "This invitation is not valid.")
    try:
        dependent_id = uuid.UUID(payload["sub"])
        inviter_id = uuid.UUID(payload["inviter"])
        phone = payload["phone"]
    except (KeyError, ValueError, TypeError):
        raise AppError(400, "INVITE_INVALID", "This invitation is not valid.")
    # The inviter must still be this Dependent's Primary Guardian.
    if not _is_primary_of(db, inviter_id, dependent_id):
        raise AppError(400, "INVITE_INVALID", "This invitation is not valid.")
    return {"dependent_id": dependent_id, "inviter_id": inviter_id, "phone": phone}


def attach_secondary(db: Session, guardian_id: uuid.UUID, dependent_id: uuid.UUID) -> GuardianDependentLink:
    """
    Add a Secondary link, enforcing the cap under a row lock. Does NOT commit: the
    caller (register-with-invite, or accept-invite) commits, so account creation and
    linking succeed or fail together.
    """
    _lock_dependent(db, dependent_id)
    links = _active_links(db, dependent_id)
    if any(l.guardian_id == guardian_id for l in links):
        raise AppError(409, "ALREADY_LINKED", "You are already linked to this Dependent.")
    if len(links) >= MAX_GUARDIANS:
        raise AppError(409, "GUARDIAN_CAP_REACHED", "This Dependent already has the maximum of 3 Guardians.")
    return _insert_link(db, guardian_id, dependent_id, "secondary")


def accept_invite(db: Session, user: User, token: str) -> LinkOut:
    """For a Secondary-designated account that already exists (FR-B4: many Dependents)."""
    profile = _guardian_profile(db, user)
    if profile.guardian_role != "secondary":
        raise AppError(
            403,
            "PRIMARY_CANNOT_ACCEPT_INVITE",
            "A Primary Guardian account cannot accept a Secondary invitation (FR-A1).",
        )
    invite = read_invite(db, token)
    if invite["phone"] != user.phone:
        raise AppError(403, "INVITE_NOT_FOR_YOU", "This invitation was sent to a different phone number.")
    link = attach_secondary(db, user.user_id, invite["dependent_id"])
    db.commit()
    db.refresh(link)
    return _link_out(link)


# ---------------------------------------------------------------------- listing


def list_my_dependents(db: Session, user: User) -> list[DependentSummary]:
    from app.services import auth_service  # lazy: auth_service imports this module

    _guardian_profile(db, user)
    links = db.scalars(
        select(GuardianDependentLink)
        .where(GuardianDependentLink.guardian_id == user.user_id, GuardianDependentLink.status == ACTIVE)
        .order_by(GuardianDependentLink.linked_at)
    ).all()
    out = []
    for link in links:
        dep_user = db.get(User, link.dependent_id)
        dep_profile = db.get(DependentProfile, link.dependent_id)
        out.append(
            DependentSummary(
                dependent_id=link.dependent_id,
                email=dep_user.email,
                phone=dep_user.phone,
                my_role=link.role,
                kyc_status=dep_profile.liveness_status,
                account_active=auth_service.is_account_active(db, dep_user),
                linked_at=link.linked_at,
            )
        )
    return out


def list_guardians(db: Session, user: User, dependent_id: uuid.UUID) -> list[GuardianSummary]:
    _guardian_profile(db, user)
    links = _active_links(db, dependent_id)
    if not any(l.guardian_id == user.user_id for l in links):
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    out = []
    for link in sorted(links, key=lambda l: (l.role != "primary", l.linked_at)):
        g_user = db.get(User, link.guardian_id)
        g_profile = db.get(GuardianProfile, link.guardian_id)
        out.append(
            GuardianSummary(
                guardian_id=link.guardian_id,
                email=g_user.email,
                phone=g_user.phone,
                guardian_role=link.role,
                verified=bool(g_profile.phone_verified or g_profile.cnic_verified),
                linked_at=link.linked_at,
            )
        )
    return out
