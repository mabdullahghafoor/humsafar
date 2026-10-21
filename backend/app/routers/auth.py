"""
Auth router (Task 1.3): POST /auth/register, POST /auth/login (SDS 11.1),
plus POST /auth/refresh (the refresh half of SDS 11.3's access+refresh pair)
and GET /auth/me (a small helper to check a token and see who it belongs to).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth_service

from app.core.ratelimit import per_ip

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201, dependencies=[Depends(per_ip("register", "RATE_REGISTER_PER_MIN"))])
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new Guardian or Dependent account. Returns the account, no tokens (log in next)."""
    user = auth_service.register_user(db, body)
    return auth_service.user_to_out(db, user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(per_ip("login", "RATE_LOGIN_PER_MIN"))])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and issue a JWT access + refresh token pair."""
    user = auth_service.authenticate(db, body.email, body.password)
    return auth_service.issue_token_pair(db, user)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(per_ip("refresh", "RATE_LOGIN_PER_MIN"))])
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a fresh access + refresh pair."""
    return auth_service.refresh_tokens(db, body.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the account the supplied access token belongs to."""
    return auth_service.user_to_out(db, user)
