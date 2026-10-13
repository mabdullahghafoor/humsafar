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
from app.models import User

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
