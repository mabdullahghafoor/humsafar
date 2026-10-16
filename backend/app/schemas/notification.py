"""Schemas for notifications and push tokens (Task 3.1, FR-M1 / FR-M2)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    notification_id: UUID
    type: str = Field(description="e.g. geofence_breach, low_battery, device_offline, panic, missed_dose, wellness_check")
    priority: Literal["standard", "critical"]
    title: str
    body: str
    dependent_id: UUID | None = None
    event_id: UUID | None = Field(default=None, description="The escalation event this is about, if any.")
    data: dict[str, Any] = Field(default_factory=dict, description="Everything stored with the notification.")
    sent_at: datetime
    acknowledged_at: datetime | None = None
    is_acknowledged: bool


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unacknowledged_critical: int = Field(description="How many critical notifications you have not acknowledged yet (all pages).")
    next_before: datetime | None = Field(default=None, description="Pass as `before` to get the next (older) page. Null = no more.")


class PushTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096, description="The phone's Firebase (FCM) registration token.")
    platform: Literal["android"] = "android"


class PushTokenOut(BaseModel):
    registered: bool = True
