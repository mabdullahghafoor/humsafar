"""
Password hashing and JWT helpers (SDS 11.3, 17).

- Passwords: bcrypt, salted, never stored or logged in plain text.
- Tokens: stateless JWT (HS256). Access token ~15 min, refresh token ~7 days.
  Every token carries a `type` claim so a refresh token can never be used as an
  access token (or the reverse).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import AppError

ACCESS = "access"
REFRESH = "refresh"

BCRYPT_ROUNDS = 12

# ----------------------------------------------------------------------------
# Passwords
# ----------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


_dummy_hash: str | None = None


def burn_password_check(plain: str) -> None:
    """
    Spend the same time as a real password check. Used when the email is unknown
    so an attacker cannot tell 'no such account' from 'wrong password' by timing.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("humsafar-timing-equaliser")
    verify_password(plain, _dummy_hash)


# ----------------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------------


def _create_token(user_id: uuid.UUID, role: str, token_type: str, lifetime: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    minutes = get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token(user_id, role, ACCESS, timedelta(minutes=minutes))


def create_refresh_token(user_id: uuid.UUID, role: str) -> str:
    days = get_settings().JWT_REFRESH_TOKEN_EXPIRE_DAYS
    return _create_token(user_id, role, REFRESH, timedelta(days=days))


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """
    Verify signature, expiry and token type. Raises AppError(401) on any problem,
    with TOKEN_EXPIRED kept distinct so the app knows to try its refresh token.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # pinned: rejects alg=none / algorithm swaps
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppError(401, "TOKEN_EXPIRED", "Your session has expired.", headers={"WWW-Authenticate": "Bearer"})
    except jwt.PyJWTError:
        raise AppError(401, "TOKEN_INVALID", "Invalid authentication token.", headers={"WWW-Authenticate": "Bearer"})

    if payload.get("type") != expected_type:
        raise AppError(
            401,
            "TOKEN_WRONG_TYPE",
            f"This endpoint needs {'an' if expected_type == 'access' else 'a'} {expected_type} token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
