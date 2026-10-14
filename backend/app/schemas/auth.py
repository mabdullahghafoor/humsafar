"""
Request/response schemas for the Auth endpoints (SDS 11.1 / 11.2).

Server-side validation mirrors what Talha's Flutter screens already check
client-side (Pakistani phone format, baseline password rule), so a valid form
is never rejected here and an invalid one gets a precise field-level error.
"""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# 03XXXXXXXXX, +923XXXXXXXXX, 923XXXXXXXXX, 00923XXXXXXXXX  (all the same number)
_PK_MOBILE = re.compile(r"^(?:\+92|0092|92|0)?(3\d{9})$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt only uses the first 72 bytes


def normalize_phone(raw: str) -> str:
    """
    Store every phone in one canonical form (E.164). Without this, 03001234567
    and +923001234567 would be two 'different' phones and the UNIQUE constraint
    on users.phone would let the same person register twice.
    """
    cleaned = re.sub(r"[\s\-()]", "", raw)
    match = _PK_MOBILE.match(cleaned)
    if match:
        return "+92" + match.group(1)
    if _E164.match(cleaned):
        return cleaned
    raise ValueError("Enter a valid phone number, e.g. 03001234567 or +923001234567.")


class RegisterRequest(BaseModel):
    email: EmailStr
    phone: str
    password: str
    role: Literal["guardian", "dependent"]
    # Task 1.5: a Secondary Guardian registers by accepting an invitation (FR-A1/FR-B1).
    invite_token: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _invite_only_for_guardians(self) -> "RegisterRequest":
        if self.invite_token and self.role != "guardian":
            raise ValueError("Invitations are for Guardian accounts only.")
        return self

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("password")
    @classmethod
    def _valid_password(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        if len(v.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError("Password is too long (maximum 72 bytes).")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserOut(BaseModel):
    user_id: UUID
    email: str
    phone: str
    role: Literal["guardian", "dependent"]
    # Only set for guardians: 'primary' | 'secondary' (FR-A1, fixed at account level).
    guardian_role: str | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    user: UserOut
