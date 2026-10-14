"""Request/response schemas for the KYC endpoints (Task 1.4)."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_CNIC = re.compile(r"^(\d{5})-?(\d{7})-?(\d)$")

KycStatus = Literal["verified", "pending", "failed"]


def normalize_cnic(raw: str) -> str:
    """13 digits, with or without dashes, stored as 12345-1234567-1 (fits String(15))."""
    match = _CNIC.match(raw.strip())
    if not match or match.group(1)[0] == "0":
        raise ValueError("Enter a valid 13-digit CNIC, e.g. 42101-1234567-1.")
    return "-".join(match.groups())


class _CnicMixin(BaseModel):
    cnic: str

    @field_validator("cnic")
    @classmethod
    def _clean_cnic(cls, v: str) -> str:
        return normalize_cnic(v)


class DependentKycRequest(_CnicMixin):
    # No JWT can exist for an un-activated Dependent (SDS 11.3), so the Dependent
    # re-proves who they are with their password. See docs/sds_clarifications.md.
    password: str = Field(min_length=1, max_length=128)
    # Base64 photo from the liveness capture. Not stored (the SDS has no column for it).
    liveness_image: str = Field(min_length=1, max_length=3_000_000)


class DependentKycResponse(BaseModel):
    status: KycStatus
    message: str
    account_active: bool
    next_step: Literal["link_primary_guardian", "none", "retry"]


class GuardianCnicRequest(_CnicMixin):
    pass


class OtpRequestResponse(BaseModel):
    sent: bool
    expires_in: int
    dev_otp: str | None = None  # only present when ENVIRONMENT == development


class OtpConfirmRequest(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class GuardianVerificationOut(BaseModel):
    verified: bool
    phone_verified: bool
    cnic_verified: bool
    status: KycStatus | None = None  # outcome of the call that just happened, when relevant
