"""
KYC business logic (Task 1.4, FR-A2 / FR-A3).

Dependent: the existing `dependent_profiles.liveness_status` column is the single
verification state. It becomes 'verified' only when BOTH the CNIC check and the
liveness check pass, so Task 1.3's activation rule (liveness_status == 'verified'
plus an active Primary link) needs no change.

Guardian: verified when phone OTP OR CNIC passes (FR-A3 says "and/or"). The SDS
guardian_profiles table has no CNIC number column, so only the boolean outcome
(`cnic_verified`) is stored, which also avoids keeping the number at all.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ratelimit, security
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import DependentProfile, GuardianProfile, User
from app.schemas.kyc import (
    DependentKycRequest,
    DependentKycResponse,
    GuardianVerificationOut,
    OtpRequestResponse,
)
from app.services import auth_service
from app.services.kyc_provider import FAILED, PENDING, VERIFIED, KycProvider

OTP_VALID_SECONDS = 300


def _bad_credentials() -> AppError:
    # One answer for unknown id, wrong role and wrong password: no account probing.
    return AppError(401, "INVALID_CREDENTIALS", "Incorrect credentials.")


def verify_dependent(
    db: Session, provider: KycProvider, dependent_id: uuid.UUID, data: DependentKycRequest
) -> DependentKycResponse:
    st = get_settings()
    ratelimit.blocked("kyc_fail", str(dependent_id), st.OTP_FAIL_LIMIT, st.OTP_FAIL_WINDOW_S)  # wrong passwords here would be password guessing
    user = db.get(User, dependent_id)
    if user is None or user.role != "dependent":
        security.burn_password_check(data.password)
        ratelimit.fail("kyc_fail", str(dependent_id))
        raise _bad_credentials()
    if not security.verify_password(data.password, user.password_hash):
        ratelimit.fail("kyc_fail", str(dependent_id))
        raise _bad_credentials()
    ratelimit.clear("kyc_fail", str(dependent_id))

    profile = db.get(DependentProfile, dependent_id)
    if profile is None:
        raise _bad_credentials()

    if profile.liveness_status == VERIFIED:
        raise AppError(409, "ALREADY_VERIFIED", "This account is already verified.")

    # Another account must not reuse this CNIC (FR-A2's purpose: no fake/duplicate Dependents).
    taken = db.scalar(
        select(DependentProfile.user_id).where(
            DependentProfile.cnic == data.cnic, DependentProfile.user_id != dependent_id
        )
    )
    if taken:
        raise AppError(409, "CNIC_ALREADY_REGISTERED", "This CNIC is already registered to another account.")

    previously_submitted = profile.cnic == data.cnic
    cnic_result = provider.check_cnic(data.cnic, previously_submitted)
    liveness_result = provider.check_liveness(data.liveness_image)

    if FAILED in (cnic_result.status, liveness_result.status):
        status = FAILED
    elif PENDING in (cnic_result.status, liveness_result.status):
        status = PENDING
    else:
        status = VERIFIED

    profile.cnic = data.cnic
    profile.liveness_status = status
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "CNIC_ALREADY_REGISTERED", "This CNIC is already registered to another account.")

    active = auth_service.is_account_active(db, user)
    if status == VERIFIED:
        message = (
            "Verified. Your account is active."
            if active
            else "Verified. Your account activates once your Primary Guardian links you."
        )
        next_step = "none" if active else "link_primary_guardian"
    elif status == PENDING:
        message = cnic_result.reason or liveness_result.reason or "Verification is pending."
        next_step = "retry"
    else:
        message = cnic_result.reason if cnic_result.status == FAILED else liveness_result.reason
        next_step = "retry"
    return DependentKycResponse(status=status, message=message, account_active=active, next_step=next_step)


# ---------------------------------------------------------------- guardians


def _guardian_profile(db: Session, user: User) -> GuardianProfile:
    profile = db.get(GuardianProfile, user.user_id)
    if profile is None:
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    return profile


def is_guardian_verified(profile: GuardianProfile) -> bool:
    return bool(profile.phone_verified or profile.cnic_verified)


def guardian_status(db: Session, user: User, status: str | None = None) -> GuardianVerificationOut:
    profile = _guardian_profile(db, user)
    return GuardianVerificationOut(
        verified=is_guardian_verified(profile),
        phone_verified=profile.phone_verified,
        cnic_verified=profile.cnic_verified,
        status=status,
    )


def request_guardian_otp(db: Session, provider: KycProvider, user: User) -> OtpRequestResponse:
    _guardian_profile(db, user)
    provider.send_otp(user.phone)
    dev = get_settings().ENVIRONMENT == "development"
    return OtpRequestResponse(
        sent=True,
        expires_in=OTP_VALID_SECONDS,
        dev_otp=get_settings().MOCK_OTP_CODE if dev else None,
    )


def confirm_guardian_otp(db: Session, provider: KycProvider, user: User, code: str) -> GuardianVerificationOut:
    profile = _guardian_profile(db, user)
    st = get_settings()
    ratelimit.blocked("otp_fail", str(user.user_id), st.OTP_FAIL_LIMIT, st.OTP_FAIL_WINDOW_S)  # a 6-digit code must not be guessable
    if not provider.check_otp(user.phone, code):
        ratelimit.fail("otp_fail", str(user.user_id))
        raise AppError(400, "OTP_INVALID", "That code is incorrect or has expired.")
    ratelimit.clear("otp_fail", str(user.user_id))
    profile.phone_verified = True
    db.commit()
    return guardian_status(db, user, VERIFIED)


def verify_guardian_cnic(db: Session, provider: KycProvider, user: User, cnic: str) -> GuardianVerificationOut:
    profile = _guardian_profile(db, user)
    # Guardians have no stored CNIC to remember a first submission by, so a guardian
    # CNIC check is always final: verified or failed, never left pending.
    st = get_settings()
    ratelimit.blocked("cnic_fail", str(user.user_id), st.OTP_FAIL_LIMIT * 2, st.OTP_FAIL_WINDOW_S)
    result = provider.check_cnic(cnic, previously_submitted=True)
    if result.status != VERIFIED:
        ratelimit.fail("cnic_fail", str(user.user_id))
    if result.status == VERIFIED:
        profile.cnic_verified = True
        db.commit()
    return guardian_status(db, user, result.status)
