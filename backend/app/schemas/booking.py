"""Schemas for home-care booking requests and the shared Activity Timeline (Task 6.2, FR-J1, FR-I2/J2)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.schemas.directory import ChargeUnit

BookingStatus = Literal["pending", "confirmed", "completed", "cancelled"]
ActivityType = Literal["org_contact", "booking_request", "booking_confirmed", "booking_completed", "booking_cancelled"]


def _clean(v: str | None) -> str | None:
    if isinstance(v, str) and "\x00" in v:
        raise ValueError("This text contains a character that is not allowed.")
    v = v.strip() if isinstance(v, str) else v
    return v or None


class BookingIn(BaseModel):
    provider_id: UUID
    preferred_at: AwareDatetime | None = Field(default=None, description="When the visit is wanted, with a time zone. Optional. Must be in the future, within a year.")
    note: str | None = Field(default=None, max_length=300, description="What is needed, for example 'injection every morning for 5 days'.")
    client_id: UUID | None = Field(default=None, description="A random id for safe retry: the same id never makes two requests.")

    _n = field_validator("note")(_clean)


class ContactIn(BaseModel):
    org_id: UUID


class BookingOut(BaseModel):
    request_id: UUID
    dependent_id: UUID
    provider_id: UUID
    provider_name: str
    specialization: str
    contact: str = Field(description="The provider's contact: the app opens the dialer. The platform does not message the provider.")
    service_charge: float | None = None
    charge_unit: ChargeUnit
    status: BookingStatus
    requested_by: UUID
    requested_by_name: str
    requested_at: datetime
    preferred_at: datetime | None = None
    note: str | None = None
    updated_at: datetime
    already_saved: bool = Field(default=False, description="true when this was a retry of a request that was already saved.")


class BookingList(BaseModel):
    items: list[BookingOut]
    total: int
    limit: int
    offset: int


class Initiator(BaseModel):
    user_id: UUID
    full_name: str
    role: Literal["dependent", "primary", "secondary", "former_guardian"]


class ActivityOut(BaseModel):
    activity_id: UUID
    dependent_id: UUID
    type: ActivityType
    occurred_at: datetime
    initiated_by: Initiator
    subject_name: str = Field(description="The organization or provider, as named at that moment.")
    reference_id: UUID | None = Field(default=None, description="org_contact: the organization id. booking_*: the booking request id.")
    booking_status: BookingStatus | None = Field(default=None, description="booking_*: the request's status now (the entry itself never changes).")


class ActivityList(BaseModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int
