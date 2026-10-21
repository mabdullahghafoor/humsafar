"""Analytics dashboard (Task 7.1, FR-Q1): adherence and vitals trends for a Guardian."""

import uuid
from datetime import date as DateType
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Trend = Literal["rising", "falling", "steady", "not_enough_data"]
AdherenceChange = Literal["improving", "declining", "steady", "not_enough_data"]


class AdherencePeriod(BaseModel):
    taken: int
    missed: int
    rate_percent: float | None = Field(description="taken / (taken + missed) x 100, or null when no dose has been decided yet.")


class AdherenceDay(BaseModel):
    date: DateType = Field(description="Local day (MEDICATION_TIMEZONE).")
    taken: int
    missed: int
    rate_percent: float | None


class AdherenceMedicine(BaseModel):
    drug_name: str
    dosage: str
    taken: int
    missed: int
    rate_percent: float | None


class AdherenceReport(BaseModel):
    days: int
    from_date: DateType
    to_date: DateType
    timezone: str
    taken: int
    missed: int
    waiting: int = Field(description="Doses whose time has come but are not yet confirmed or missed. Not counted in the rate.")
    rate_percent: float | None
    previous: AdherencePeriod = Field(description="The same number of days just before this period.")
    change_points: float | None = Field(description="rate_percent minus previous rate_percent, or null when either is missing.")
    change: AdherenceChange
    perfect_days_in_a_row: int = Field(description="Days in a row, counting back from today, with at least one decided dose and no missed dose. Days with no doses are skipped.")
    daily: list[AdherenceDay] = Field(description="One entry for every day in the period, oldest first.")
    by_medicine: list[AdherenceMedicine]


class VitalDay(BaseModel):
    date: DateType
    count: int
    avg: float
    min: float
    max: float
    avg_diastolic: float | None = None
    min_diastolic: float | None = None
    max_diastolic: float | None = None


class VitalLatest(BaseModel):
    value: float
    diastolic: float | None = None
    recorded_at: datetime
    source: Literal["manual", "wearable"]


class VitalMetricReport(BaseModel):
    metric_type: str
    unit: str
    count: int
    manual_count: int
    wearable_count: int
    avg: float | None = None
    min: float | None = None
    max: float | None = None
    avg_diastolic: float | None = None
    min_diastolic: float | None = None
    max_diastolic: float | None = None
    latest: VitalLatest | None = None
    trend: Trend = Field(description="Average of the second half of the period against the first half. Describes the numbers only; it never says good or bad.")
    change_percent: float | None = Field(default=None, description="Second-half average against first-half average, in percent (blood pressure: the top number).")
    daily: list[VitalDay] = Field(description="Only days that have readings, oldest first.")


class VitalsReport(BaseModel):
    days: int
    from_date: DateType
    to_date: DateType
    timezone: str
    metrics: list[VitalMetricReport]


class AnalyticsOverview(BaseModel):
    dependent_id: uuid.UUID
    days: int
    adherence: AdherenceReport | None = Field(description="Null when the Guardian does not have the medication_management permission.")
    vitals: VitalsReport | None = Field(description="Null when the Guardian does not have the health_records permission.")
