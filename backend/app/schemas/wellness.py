"""Request/response schemas for the Guardian wellness check (Task 3.4, FR-D4)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.medication import _hhmm

MIN_GRACE_MIN = 5
MAX_GRACE_MIN = 180
DEFAULT_GRACE_MIN = 30
DEFAULT_TIMES = ("08:00", "14:00", "20:00")  # the default schedule (SRS FR-D4: "up to three per day")

ResponseStatus = Literal["pending", "responded", "device_active", "escalated", "cancelled"]
Tier = Literal["primary", "secondary", "external_contact"]


class WellnessIn(BaseModel):
    times: list[str] = Field(min_length=1, max_length=3, description="Check times in local time, e.g. ['08:00','20:00'].")
    grace_period_min: int = Field(default=DEFAULT_GRACE_MIN, ge=MIN_GRACE_MIN, le=MAX_GRACE_MIN)

    @field_validator("times")
    @classmethod
    def _t(cls, v: list[str]) -> list[str]:
        return sorted({_hhmm(x) for x in v})


class WellnessUpdate(BaseModel):
    time: str | None = None
    grace_period_min: int | None = Field(default=None, ge=MIN_GRACE_MIN, le=MAX_GRACE_MIN)
    active: bool | None = None

    @field_validator("time")
    @classmethod
    def _t(cls, v):
        return None if v is None else _hhmm(v)


class WellnessOut(BaseModel):
    wc_id: UUID
    dependent_id: UUID
    time: str  # "HH:MM", local time
    grace_period_min: int
    active: bool
    created_at: datetime


class WellnessListOut(BaseModel):
    timezone: str
    default_times: list[str]
    default_grace_period_min: int
    items: list[WellnessOut]


class CheckResponseOut(BaseModel):
    response_id: UUID
    wc_id: UUID
    prompted_at: datetime
    deadline: datetime  # the Dependent should answer before this
    status: ResponseStatus
    responded_at: datetime | None
    open_alert_tier: Tier | None = None  # set while a "not answered" alert is open


class CheckResponseListOut(BaseModel):
    items: list[CheckResponseOut]


class RespondOut(BaseModel):
    response_id: UUID
    status: ResponseStatus
    responded_at: datetime
    already_responded: bool
