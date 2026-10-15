"""Request/response schemas for geofences and breach status (Task 2.2, FR-C2 / FR-C3)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MIN_RADIUS_M = 50.0  # smaller than normal GPS error, would cause false breaches
MAX_RADIUS_M = 50000.0

GeofenceState = Literal["no_zones", "inside", "outside", "unknown"]


class GeofenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_m: float = Field(ge=MIN_RADIUS_M, le=MAX_RADIUS_M, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class GeofenceOut(BaseModel):
    geofence_id: UUID
    dependent_id: UUID
    name: str
    lat: float
    lng: float
    radius_m: float
    created_by: UUID


class GeofenceListOut(BaseModel):
    dependent_id: UUID
    count: int
    max_zones: int
    geofences: list[GeofenceOut]


class GeofenceStatusOut(BaseModel):
    """Where the Dependent is relative to the safe zones, as of their newest fix."""

    dependent_id: UUID
    status: GeofenceState  # unknown = no location yet, or the newest fix is too old to judge
    inside_zone_ids: list[UUID]
    breach_open: bool
    breach_event_id: UUID | None
    breach_since: datetime | None
