"""Summary reports (Task 7.2, FR-Q2)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Frequency = Literal["weekly", "monthly"]


class ScheduleIn(BaseModel):
    frequency: Frequency


class ScheduleOut(BaseModel):
    dependent_id: uuid.UUID
    frequency: Frequency | None = Field(description="null = no automatic report.")
    since: datetime | None = Field(default=None, description="When this schedule was switched on. Only periods that end after this are made.")


class ReportCreateIn(BaseModel):
    days: int = Field(default=7, ge=7, le=90, description="How many days back from today the report covers (7 to 90).")


class ReportOut(BaseModel):
    report_id: uuid.UUID
    dependent_id: uuid.UUID
    period: Literal["weekly", "monthly", "custom"]
    source: Literal["scheduled", "manual"]
    period_start: date
    period_end: date
    includes_adherence: bool
    includes_vitals: bool
    size_bytes: int
    created_at: datetime
    file_name: str


class ReportList(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int
