"""Request/response schemas for guardian-dependent linkage (Task 1.5, FR-B1/B2/B4)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import normalize_phone


class LinkOut(BaseModel):
    link_id: UUID
    dependent_id: UUID
    guardian_id: UUID
    role: Literal["primary", "secondary"]
    status: str
    linked_at: datetime


class InviteRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        return normalize_phone(v)


class InviteOut(BaseModel):
    invite_token: str
    invited_phone: str
    expires_at: datetime
    expires_in: int


class AcceptInviteRequest(BaseModel):
    invite_token: str = Field(min_length=1, max_length=2000)


class DependentSummary(BaseModel):
    dependent_id: UUID
    email: str
    phone: str
    my_role: Literal["primary", "secondary"]
    kyc_status: str
    account_active: bool
    linked_at: datetime


class GuardianSummary(BaseModel):
    guardian_id: UUID
    email: str
    phone: str
    guardian_role: Literal["primary", "secondary"]
    verified: bool
    linked_at: datetime
