"""Escalation chain schemas (Task 3.5, FR-D5)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

EventStatus = Literal["open", "resolved"]


class EscalationOut(BaseModel):
    event_id: UUID
    trigger_type: str
    reference_id: UUID | None
    tier: str  # primary | secondary | external_contact
    status: str  # open | resolved
    created_at: datetime
    tier_changed_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    resolved_at: datetime | None
    next_escalation_at: datetime | None  # when the server will move it up a level; null if it will not


class EscalationListOut(BaseModel):
    primary_timeout_s: int
    secondary_timeout_s: int
    items: list[EscalationOut]
