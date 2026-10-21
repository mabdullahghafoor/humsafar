"""Request/response schemas for location ingestion and reading (Task 2.1, FR-C1, FR-C4)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MovementState = Literal["moving", "stationary", "idle"]


class LocationUpdateRequest(BaseModel):
    """One GPS fix sent by the Dependent's phone."""

    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    recorded_at: datetime | None = None  # when the phone took the fix; default = server time now
    battery_level: int | None = Field(default=None, ge=0, le=100)  # percent; feeds FR-L1
    speed_mps: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)  # from the phone GPS, optional
    accuracy_m: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)  # GPS error radius, optional

    @field_validator("recorded_at")
    @classmethod
    def _needs_timezone(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("recorded_at must include a timezone, e.g. 2026-10-16T09:30:00Z")
        return v


class LocationAck(BaseModel):
    """What the phone gets back: how it should behave next (the adaptive part of FR-C1)."""

    log_id: UUID
    recorded_at: datetime
    movement_state: MovementState
    next_update_interval_s: int
    duplicate: bool = False  # true when this exact fix was already stored (a safe retry)
    geofence_status: Literal["no_zones", "inside", "outside"] = "no_zones"  # FR-C2/C3, judged on this fix
    breach_started: bool = False  # true only on the fix that opened a new geofence breach
    low_battery: bool = False  # a low-battery alert is open (battery <= 15%, FR-L1)
    low_battery_started: bool = False  # true only on the fix that opened it


class LocationPoint(BaseModel):
    lat: float
    lng: float
    recorded_at: datetime
    battery_level: int | None


class LatestLocationOut(BaseModel):
    dependent_id: UUID
    location: LocationPoint | None  # null until the Dependent has sent a first fix
    age_seconds: int | None
    is_stale: bool  # true when there is no fix, or the newest one is older than the stale threshold


class LocationHistoryOut(BaseModel):
    dependent_id: UUID
    count: int
    points: list[LocationPoint]  # newest first
