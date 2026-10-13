"""
Auth service: the business logic behind the SDS 'AuthController' component
(registration, login, token issuance). Routers stay thin and call into here.

Account-activation rules implemented (SRS/SDS):
- Guardian (FR-A1): can log in right after registering. Registering independently
  makes the account 'primary'; 'secondary' is only ever set by accepting an
  invitation (Task 1.5). Guardian identity verification (FR-A3) is enforced by
  a separate gate on intervention features (Task 1.4), not at login.
- Dependent (FR-A2, SDS 11.3): no token is issued until KYC has succeeded
  (liveness_status == 'verified') AND the Dependent is linked to exactly one
  active Primary Guardian. Until then login returns ACCOUNT_NOT_ACTIVATED.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import DependentProfile, GuardianDependentLink, GuardianProfile, User
from app.schemas.auth import RegisterRequest, UserOut

# What KYC (Task 1.4) must set on dependent_profiles.liveness_status on success.
KYC_VERIFIED = "verified"


def user_to_out(db: Session, user: User) -> UserOut:
    guardian_role = None
    if user.role == "guardian":
        profile = db.get(GuardianProfile, user.user_id)
        guardian_role = profile.guardian_role if profile else None
    return UserOut(
        user_id=user.user_id,
        email=user.email,
        phone=user.phone,
        role=user.role,
        guardian_role=guardian_role,
        created_at=user.created_at,
    )


def register_user(db: Session, data: RegisterRequest) -> User:
    if db.scalar(select(User.user_id).where(User.email == data.email)):
        raise AppError(409, "EMAIL_ALREADY_REGISTERED", "An account with this email already exists.")
    if db.scalar(select(User.user_id).where(User.phone == data.phone)):
        raise AppError(409, "PHONE_ALREADY_REGISTERED", "An account with this phone number already exists.")

    user = User(
        email=data.email,
        phone=data.phone,
        password_hash=security.hash_password(data.password),
        role=data.role,
    )
    try:
        db.add(user)
        db.flush()  # assigns user.user_id so the profile row can reference it
        if data.role == "guardian":
            db.add(GuardianProfile(user_id=user.user_id, guardian_role="primary"))
        else:
            db.add(DependentProfile(user_id=user.user_id))
        db.commit()
    except IntegrityError:
        # Two registrations racing past the pre-checks above.
        db.rollback()
        raise AppError(409, "ALREADY_REGISTERED", "An account with these details already exists.")

    db.refresh(user)
    return user


def is_account_active(db: Session, user: User) -> bool:
    if user.role == "guardian":
        return True
    profile = db.get(DependentProfile, user.user_id)
    if profile is None or profile.liveness_status != KYC_VERIFIED:
        return False
    primary_link = db.scalar(
        select(GuardianDependentLink.link_id).where(
            GuardianDependentLink.dependent_id == user.user_id,
            GuardianDependentLink.role == "primary",
            GuardianDependentLink.status == "active",
        )
    )
    return primary_link is not None


def _require_active(db: Session, user: User) -> None:
    if not is_account_active(db, user):
        raise AppError(
            403,
            "ACCOUNT_NOT_ACTIVATED",
            "This account is not active yet. It needs identity verification and a linked Primary Guardian.",
        )


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        security.burn_password_check(password)  # same timing as a real check
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    if not security.verify_password(password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    # Only reveal activation state to someone who proved they know the password.
    _require_active(db, user)
    return user


def issue_token_pair(db: Session, user: User) -> dict:
    return {
        "access_token": security.create_access_token(user.user_id, user.role),
        "refresh_token": security.create_refresh_token(user.user_id, user.role),
        "token_type": "bearer",
        "expires_in": get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_to_out(db, user),
    }


def refresh_tokens(db: Session, refresh_token: str) -> dict:
    payload = security.decode_token(refresh_token, security.REFRESH)
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except ValueError:
        user = None
    if user is None:
        raise AppError(401, "TOKEN_INVALID", "Invalid authentication token.", headers={"WWW-Authenticate": "Bearer"})
    _require_active(db, user)
    return issue_token_pair(db, user)  # rotation: a fresh pair every refresh
