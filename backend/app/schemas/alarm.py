"""Remote Alarm Override schemas (Task 3.7, FR-D3)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AlarmIn(BaseModel):
    duration_s: int | None = Field(default=None, description="How long the alarm sounds, 10 to 300 seconds. Default 60.")

    @field_validator("duration_s")
    @classmethod
    def _range(cls, v):
        from app.core.config import get_settings

        s = get_settings()
        if v is not None and not (s.ALARM_MIN_S <= v <= s.ALARM_MAX_S):
            raise ValueError(f"duration_s must be between {s.ALARM_MIN_S} and {s.ALARM_MAX_S}")
        return v


class AlarmOut(BaseModel):
    alarm_id: UUID
    status: str  # active | stopped | expired
    triggered_by: UUID
    triggered_at: datetime
    duration_s: int
    expires_at: datetime
    stopped_at: datetime | None
    device_acknowledged_at: datetime | None  # the Dependent's phone opened the alert
    already_active: bool = False  # true when an alarm was already sounding (nothing new was sent)


class AlarmStatusOut(BaseModel):
    active: bool
    alarm: AlarmOut | None
