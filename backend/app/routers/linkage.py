"""
Linkage router (Task 1.5, FR-B1 / FR-B2 / FR-B4).

SDS 11.1:  POST /dependents/{id}/link
           POST /dependents/{id}/guardians/invite
Added:     GET  /dependents/{id}/guardians      (who is linked, for the dashboard)
           GET  /guardians/me/dependents        (FR-B4: switch between Dependents)
           POST /invitations/accept             (an existing Secondary accepts another invitation)
Secondary accounts are created through POST /auth/register with an invite_token.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role, require_verified_guardian
from app.models import User
from app.schemas.linkage import (
    AcceptInviteRequest,
    DependentSummary,
    GuardianSummary,
    InviteOut,
    InviteRequest,
    LinkOut,
)
from app.services import linkage_service

dependents_router = APIRouter(prefix="/dependents", tags=["Linkage"])
guardians_router = APIRouter(prefix="/guardians/me", tags=["Linkage"])
invitations_router = APIRouter(prefix="/invitations", tags=["Linkage"])


@dependents_router.post("/{dependent_id}/link", response_model=LinkOut, status_code=201)
def link_dependent(
    dependent_id: uuid.UUID, user: User = Depends(require_verified_guardian), db: Session = Depends(get_db)
):
    """A verified Primary Guardian links themselves to a Dependent."""
    return linkage_service.link_primary(db, user, dependent_id)


@dependents_router.post("/{dependent_id}/guardians/invite", response_model=InviteOut)
def invite_guardian(
    dependent_id: uuid.UUID,
    body: InviteRequest,
    user: User = Depends(require_verified_guardian),
    db: Session = Depends(get_db),
):
    """The Primary Guardian invites a Secondary Guardian by phone number. Returns a token to share."""
    return linkage_service.create_invite(db, user, dependent_id, body.phone)


@dependents_router.get("/{dependent_id}/guardians", response_model=list[GuardianSummary])
def dependent_guardians(
    dependent_id: uuid.UUID, user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)
):
    """Every active Guardian of this Dependent. Visible to Guardians linked to them."""
    return linkage_service.list_guardians(db, user, dependent_id)


@guardians_router.get("/dependents", response_model=list[DependentSummary])
def my_dependents(user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)):
    """Every Dependent this Guardian is linked to."""
    return linkage_service.list_my_dependents(db, user)


@invitations_router.post("/accept", response_model=LinkOut, status_code=201)
def accept_invitation(
    body: AcceptInviteRequest, user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)
):
    """An existing Secondary Guardian accepts an invitation for another Dependent."""
    return linkage_service.accept_invite(db, user, body.invite_token)
