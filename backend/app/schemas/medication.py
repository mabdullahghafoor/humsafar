"""Request/response schemas for medication schedules and dose confirmation (Task 3.2, FR-F1)."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Frequency = Literal["daily", "weekly"]
DoseStatus = Literal["pending", "taken", "missed"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _clean(v: str, what: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError(f"{what} must not be blank")
    return v


def _hhmm(v: str) -> str:
    v = v.strip()
    if not _HHMM.match(v):
        raise ValueError("time must look like 08:30 (24-hour, HH:MM)")
    return v


class MedicationIn(BaseModel):
    drug_name: str = Field(min_length=1, max_length=150)
    dosage: str = Field(min_length=1, max_length=100)
    times: list[str] = Field(min_length=1, max_length=6, description="Dose times in local time, e.g. ['08:00','20:00'].")
    frequency: Frequency = "daily"
    days: list[Day] | None = Field(default=None, description="Only for weekly: which days.")

    @field_validator("drug_name")
    @classmethod
    def _n(cls, v: str) -> str:
        return _clean(v, "drug_name")

    @field_validator("dosage")
    @classmethod
    def _d(cls, v: str) -> str:
        return _clean(v, "dosage")

    @field_validator("times")
    @classmethod
    def _t(cls, v: list[str]) -> list[str]:
        out = sorted({_hhmm(x) for x in v})  # duplicates collapse
        return out

    @model_validator(mode="after")
    def _freq(self):
        if self.frequency == "weekly" and not self.days:
            raise ValueError("days is required when frequency is 'weekly'")
        if self.frequency == "daily" and self.days:
            raise ValueError("days is only used when frequency is 'weekly'")
        return self


class MedicationUpdate(BaseModel):
    drug_name: str | None = Field(default=None, min_length=1, max_length=150)
    dosage: str | None = Field(default=None, min_length=1, max_length=100)
    time: str | None = None
    frequency: Frequency | None = None
    days: list[Day] | None = None
    active: bool | None = None

    @field_validator("drug_name")
    @classmethod
    def _n(cls, v):
        return None if v is None else _clean(v, "drug_name")

    @field_validator("dosage")
    @classmethod
    def _d(cls, v):
        return None if v is None else _clean(v, "dosage")

    @field_validator("time")
    @classmethod
    def _t(cls, v):
        return None if v is None else _hhmm(v)


class MedicationOut(BaseModel):
    schedule_id: UUID
    dependent_id: UUID
    drug_name: str
    dosage: str
    time: str  # "HH:MM", local time
    frequency: Frequency
    days: list[Day] | None
    active: bool
    created_by: UUID
    created_at: datetime


class MedicationListOut(BaseModel):
    timezone: str
    items: list[MedicationOut]


class DoseOut(BaseModel):
    confirmation_id: UUID
    schedule_id: UUID
    drug_name: str
    dosage: str
    scheduled_for: datetime
    status: DoseStatus
    confirmed_at: datetime | None
    window_ends_at: datetime  # after this, an unconfirmed dose is "missed" (later if a Guardian gave more time)
    open_alert_tier: Literal["primary", "secondary", "external_contact"] | None = None  # set while a missed-dose alert is open


class DoseListOut(BaseModel):
    items: list[DoseOut]


class ConfirmRequestIn(BaseModel):
    confirmation_id: UUID | None = Field(default=None, description="Optional: a specific dose. Default: the dose that is due now.")


class ConfirmRequestOut(BaseModel):
    confirmation_id: UUID
    drug_name: str
    dosage: str
    scheduled_for: datetime
    confirm_token: str
    expires_in_s: int


class ConfirmIn(BaseModel):
    confirm_token: str = Field(min_length=10, max_length=2000)


class ConfirmOut(BaseModel):
    confirmation_id: UUID
    schedule_id: UUID
    status: DoseStatus
    confirmed_at: datetime
    already_confirmed: bool


class ExtendIn(BaseModel):
    minutes: int = Field(default=30, ge=5, le=120, description="How many minutes of extra time to give.")


class EscalateOut(BaseModel):
    confirmation_id: UUID
    event_id: UUID
    tier: Literal["primary", "secondary", "external_contact"]
    notified: int  # how many people were just alerted (0 if no Secondary is allowed to see alerts)
