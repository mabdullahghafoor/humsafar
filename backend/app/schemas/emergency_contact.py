"""External emergency contact schemas (Task 3.8, FR-R1)."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import normalize_phone


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str

    @field_validator("name")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Enter the contact's name.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class ContactOut(BaseModel):
    contact_id: UUID
    name: str
    phone: str
