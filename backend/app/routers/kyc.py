"""
KYC router (Task 1.4, FR-A2 / FR-A3).

Dependent: POST /dependents/{id}/kyc-verify  (SDS 11.1)
Guardian:  /guardians/me/...                  (added; the SDS lists no guardian endpoint,
                                               but FR-A3 and SDS 11.3 require a verification flow)
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import User
from app.schemas.kyc import (
    DependentKycRequest,
    DependentKycResponse,
    GuardianCnicRequest,
    GuardianVerificationOut,
    OtpConfirmRequest,
    OtpRequestResponse,
)
from app.services import kyc_service
from app.services.kyc_provider import KycProvider, get_kyc_provider

dependents_router = APIRouter(prefix="/dependents", tags=["KYC"])
guardians_router = APIRouter(prefix="/guardians/me", tags=["KYC"])


@dependents_router.post("/{dependent_id}/kyc-verify", response_model=DependentKycResponse)
def kyc_verify(
    dependent_id: uuid.UUID,
    body: DependentKycRequest,
    db: Session = Depends(get_db),
    provider: KycProvider = Depends(get_kyc_provider),
):
    """
    Submit CNIC + liveness photo. Authenticated by the Dependent's password in the
    body, because an un-activated Dependent cannot hold a JWT yet (SDS 11.3).
    """
    return kyc_service.verify_dependent(db, provider, dependent_id, body)


@guardians_router.get("/verification", response_model=GuardianVerificationOut)
def verification_status(user: User = Depends(require_role("guardian")), db: Session = Depends(get_db)):
    """Is this Guardian verified (phone OTP and/or CNIC)?"""
    return kyc_service.guardian_status(db, user)


@guardians_router.post("/verify-phone/request", response_model=OtpRequestResponse)
def request_otp(
    user: User = Depends(require_role("guardian")),
    db: Session = Depends(get_db),
    provider: KycProvider = Depends(get_kyc_provider),
):
    """Send an OTP to the Guardian's registered phone (mocked: nothing is sent)."""
    return kyc_service.request_guardian_otp(db, provider, user)


@guardians_router.post("/verify-phone/confirm", response_model=GuardianVerificationOut)
def confirm_otp(
    body: OtpConfirmRequest,
    user: User = Depends(require_role("guardian")),
    db: Session = Depends(get_db),
    provider: KycProvider = Depends(get_kyc_provider),
):
    """Confirm the OTP. Marks the phone verified."""
    return kyc_service.confirm_guardian_otp(db, provider, user, body.code)


@guardians_router.post("/verify-cnic", response_model=GuardianVerificationOut)
def verify_cnic(
    body: GuardianCnicRequest,
    user: User = Depends(require_role("guardian")),
    db: Session = Depends(get_db),
    provider: KycProvider = Depends(get_kyc_provider),
):
    """Verify the Guardian's CNIC (no liveness photo needed, FR-A3)."""
    return kyc_service.verify_guardian_cnic(db, provider, user, body.cnic)
