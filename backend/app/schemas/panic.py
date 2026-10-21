"""Panic Mode schemas (Task 3.6, FR-D2)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PanicOut(BaseModel):
    event_id: UUID
    status: str  # open | resolved
    tier: str  # primary | external_contact (Task 3.5: panic tells everyone at once)
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    notified: int | None = None  # Guardians told (set when you trigger)
    already_active: bool = False  # true when a panic was already open (nothing new was sent)


class PanicStatusOut(BaseModel):
    active: bool
    panic: PanicOut | None
