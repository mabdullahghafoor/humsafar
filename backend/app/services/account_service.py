"""
Closing and reopening accounts (Task 6.7, FR-O1).

Closing does not delete anything at once. The account stops working immediately (no sign-in, links stop counting, no more alerts),
and the background job (retention_service) deletes or anonymizes the data after RETENTION_DAYS (default 60, clarification 157).
Until then the account can be reopened (clarification 158).

* A Guardian closes their own account. A Primary who still has active Dependents cannot (close the Dependents first).
* The Primary closes a Dependent's account. The Dependent cannot close it themselves (clarification 159).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import ratelimit, security
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import AuditLog, EscalationEvent, GuardianDependentLink, PushToken, RecordShare, User
from app.schemas.account import ClosureOut
from app.services import auth_service, linkage_service
from app.services import notification_service as ns

ACTIVE, CLOSED, REVOKED = "active", "closed", "revoked"
PW_SCOPE = "close_pw_fail"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_password(user: User, password: str) -> None:
    s = get_settings()
    key = str(user.user_id)
    ratelimit.blocked(PW_SCOPE, key, s.LOGIN_FAIL_LIMIT, s.LOGIN_FAIL_WINDOW_S)
    if not security.verify_password(password, user.password_hash):
        ratelimit.fail(PW_SCOPE, key)
        raise AppError(403, "WRONG_PASSWORD", "The password is not correct.")
    ratelimit.clear(PW_SCOPE, key)


def _out(user: User, status: str) -> ClosureOut:
    return ClosureOut(user_id=user.user_id, status=status, closed_at=user.closed_at, delete_after=user.delete_after)


def _lock(db: Session, user_id: uuid.UUID) -> User:
    return db.scalar(select(User).where(User.user_id == user_id).with_for_update())


def _primary_dependents(db: Session, guardian_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(GuardianDependentLink.dependent_id).where(
                GuardianDependentLink.guardian_id == guardian_id,
                GuardianDependentLink.role == "primary",
                GuardianDependentLink.status == ACTIVE,
            )
        )
    )


# ------------------------------------------------------------ a Guardian closes their own account

def close_guardian(db: Session, user: User, password: str) -> ClosureOut:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "Only a Guardian can close their own account. A Dependent's account is closed by the Primary Guardian.")
    _check_password(user, password)
    me = _lock(db, user.user_id)
    if me.closed_at is not None:
        db.rollback()
        raise AppError(409, "ALREADY_CLOSED", "This account is already closed.")
    owned = _primary_dependents(db, me.user_id)
    if owned:
        db.rollback()
        raise AppError(
            409, "CLOSE_DEPENDENTS_FIRST",
            "You are the Primary Guardian of a Dependent. Close that Dependent's account first.",
            details={"dependent_ids": [str(d) for d in owned]},
        )
    now = _now()
    links = db.scalars(
        select(GuardianDependentLink).where(GuardianDependentLink.guardian_id == me.user_id, GuardianDependentLink.status != REVOKED)
    ).all()
    told: list[tuple[uuid.UUID, uuid.UUID]] = []  # (Primary, Dependent): told after the change is saved
    for link in links:
        was_active = link.status == ACTIVE
        link.status = REVOKED
        db.add(AuditLog(actor_id=me.user_id, action="guardian_left", target_type="guardian_dependent_link", target_id=link.link_id, dependent_id=link.dependent_id))
        if was_active:
            primary = db.scalar(
                select(GuardianDependentLink.guardian_id).where(
                    GuardianDependentLink.dependent_id == link.dependent_id,
                    GuardianDependentLink.role == "primary",
                    GuardianDependentLink.status == ACTIVE,
                )
            )
            if primary:
                told.append((primary, link.dependent_id))
    db.execute(PushToken.__table__.delete().where(PushToken.user_id == me.user_id))
    me.closed_at, me.delete_after = now, now + timedelta(days=get_settings().RETENTION_DAYS)
    db.commit()
    for primary, dep_id in told:
        ns.notify(
            db, primary, "guardian_left", ns.STANDARD, "A Guardian left",
            f"{me.full_name or 'A Secondary Guardian'} closed their account and no longer has access.", dependent_id=dep_id,
        )
    return _out(me, "closed")


def reopen_guardian(db: Session, email: str, password: str) -> dict:
    """Public (the person cannot sign in). Same wrong-password limit as sign-in. Returns a normal token pair."""
    s = get_settings()
    key = email.strip().lower()
    ratelimit.blocked("login_fail", key, s.LOGIN_FAIL_LIMIT, s.LOGIN_FAIL_WINDOW_S)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        security.burn_password_check(password)
        ratelimit.fail("login_fail", key)
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    if not security.verify_password(password, user.password_hash):
        ratelimit.fail("login_fail", key)
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    ratelimit.clear("login_fail", key)
    me = _lock(db, user.user_id)
    if me.role != "guardian":
        db.rollback()
        raise AppError(403, "FORBIDDEN", "A Dependent's account is reopened by the Primary Guardian.")
    if me.closed_at is None or me.purged_at is not None:
        db.rollback()
        raise AppError(409, "NOT_CLOSED", "This account is not closed.")
    me.closed_at = me.delete_after = None
    db.commit()
    return auth_service.issue_token_pair(db, me)


# ------------------------------------------------------------ the Primary closes / reopens a Dependent

def _primary_link(db: Session, user: User, dependent_id: uuid.UUID, status: str) -> GuardianDependentLink:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    link = db.scalar(
        select(GuardianDependentLink).where(
            GuardianDependentLink.guardian_id == user.user_id,
            GuardianDependentLink.dependent_id == dependent_id,
            GuardianDependentLink.status == status,
        )
    )
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    if link.role != "primary":
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can do this.")
    profile = linkage_service._guardian_profile(db, user)
    if not (profile.phone_verified or profile.cnic_verified):
        raise AppError(403, "GUARDIAN_NOT_VERIFIED", "Verify your phone number or CNIC before using this feature.")
    return link


def close_dependent(db: Session, user: User, dependent_id: uuid.UUID, password: str) -> ClosureOut:
    _primary_link(db, user, dependent_id, ACTIVE)
    _check_password(user, password)
    dep = _lock(db, dependent_id)
    if dep.closed_at is not None:
        db.rollback()
        raise AppError(409, "ALREADY_CLOSED", "This account is already closed.")
    now = _now()
    others = [g for g in ns.recipients(db, dependent_id, ns.ALL_LINKED) if g != user.user_id]
    links = db.scalars(
        select(GuardianDependentLink).where(GuardianDependentLink.dependent_id == dependent_id, GuardianDependentLink.status == ACTIVE)
    ).all()
    for link in links:
        link.status = CLOSED  # not revoked: reopening within the period puts these back
    db.execute(
        update(EscalationEvent)
        .where(EscalationEvent.dependent_id == dependent_id, EscalationEvent.status == "open")
        .values(status="resolved", resolved_at=now)
    )
    db.execute(update(RecordShare).where(RecordShare.dependent_id == dependent_id, RecordShare.revoked_at.is_(None)).values(revoked_at=now))  # doctor links stop at once
    db.execute(PushToken.__table__.delete().where(PushToken.user_id == dependent_id))
    db.add(AuditLog(actor_id=user.user_id, action="dependent_account_closed", target_type="dependent", target_id=dependent_id, dependent_id=dependent_id))
    dep.closed_at, dep.delete_after = now, now + timedelta(days=get_settings().RETENTION_DAYS)
    db.commit()
    for g in others:
        ns.notify(
            db, g, "dependent_closed", ns.STANDARD, "Account closed",
            f"The Primary Guardian closed {dep.full_name or 'this Dependent'}'s account.", dependent_id=dependent_id,
        )
    return _out(dep, "closed")


def reopen_dependent(db: Session, user: User, dependent_id: uuid.UUID, password: str) -> ClosureOut:
    _primary_link(db, user, dependent_id, CLOSED)
    _check_password(user, password)
    dep = _lock(db, dependent_id)
    if dep.closed_at is None or dep.purged_at is not None:
        db.rollback()
        raise AppError(409, "NOT_CLOSED", "This account is not closed.")
    for link in db.scalars(
        select(GuardianDependentLink).where(GuardianDependentLink.dependent_id == dependent_id, GuardianDependentLink.status == CLOSED)
    ):
        link.status = ACTIVE
    db.add(AuditLog(actor_id=user.user_id, action="dependent_account_reopened", target_type="dependent", target_id=dependent_id, dependent_id=dependent_id))
    dep.closed_at = dep.delete_after = None
    db.commit()
    return _out(dep, "reopened")
