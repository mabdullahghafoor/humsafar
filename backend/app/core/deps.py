"""
Reusable FastAPI dependencies for authentication/authorization.

Every protected endpoint built from Task 1.4 onward uses:
    user: User = Depends(get_current_user)
    user: User = Depends(require_role("guardian"))
"""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import ACCESS, decode_token
from app.models import GuardianProfile, User

# auto_error=False so a missing header returns OUR error envelope, not FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /auth/login.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(
            401, "NOT_AUTHENTICATED", "Authentication required.", headers={"WWW-Authenticate": "Bearer"}
        )
    payload = decode_token(credentials.credentials, ACCESS)
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except ValueError:
        user = None
    if user is None:
        raise AppError(
            401, "TOKEN_INVALID", "Invalid authentication token.", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def require_role(*roles: str):
    """Dependency factory: only users whose account role is in `roles` get through."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return user

    return _checker


def require_verified_guardian(user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)) -> User:
    """
    FR-A3: a Guardian must be verified (phone OTP and/or CNIC) before using the
    permission dashboard or any intervention capability. Tasks 1.5+ attach this to
    those endpoints.
    """
    profile = db.get(GuardianProfile, user.user_id)
    if profile is None or not (profile.phone_verified or profile.cnic_verified):
        raise AppError(
            403,
            "GUARDIAN_NOT_VERIFIED",
            "Verify your phone number or CNIC before using this feature.",
        )
    return user


def require_module_access(module: str):
    """
    Dependency factory for every endpoint that returns a Dependent's data (FR-A4):

        @router.get("/dependents/{dependent_id}/location")
        def location(dependent_id: uuid.UUID, user: User = Depends(require_module_access("live_location"))): ...

    The path parameter must be called `dependent_id`. A Primary always passes; a Secondary
    passes only while the Primary's grant for `module` is on. Checked against the database on
    every request, so a revoke takes effect on the very next call.
    """
    # Imported inside to avoid a circular import (services import deps-free modules only).
    from app.services import permission_service

    def _checker(
        dependent_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        permission_service.check_module_access(db, user, dependent_id, module)
        return user

    return _checker
