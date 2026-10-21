"""Schemas for device health: battery and connectivity (Task 2.3, FR-L1 / FR-L2)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.location import LocationPoint

Connectivity = Literal["online", "offline", "unknown"]
ProbableCause = Literal["battery_depleted", "connectivity_or_unknown"]


class Thresholds(BaseModel):
    low_battery_pct: int
    battery_recover_pct: int
    offline_after_s: int


class DeviceHealthOut(BaseModel):
    dependent_id: UUID
    # Battery (FR-L1). Taken from the newest fix that carried a battery reading.
    battery_level: int | None
    battery_reported_at: datetime | None
    low_battery: bool  # true while a low-battery alert is open
    low_battery_since: datetime | None
    # Connectivity (FR-L2). Judged from the newest fix of any kind.
    connectivity: Connectivity  # unknown = the phone has never reported
    last_seen_at: datetime | None
    seconds_since_seen: int | None
    offline_alert_open: bool
    offline_alert_since: datetime | None  # when the system noticed, not when the phone went quiet
    probable_cause: ProbableCause | None  # only when offline
    # FR-L1.3: the position from just before contact was lost.
    last_known_location: LocationPoint | None
    thresholds: Thresholds
