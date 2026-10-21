"""Schemas for manual vitals (Task 5.3, FR-H1)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Metric = Literal["blood_pressure", "blood_sugar", "spo2", "temperature", "heart_rate"]
ManualMetric = Literal["blood_pressure", "blood_sugar", "spo2", "temperature"]
Context = Literal["fasting", "after_meal", "random"]


class VitalIn(BaseModel):
    metric_type: ManualMetric
    value: float = Field(allow_inf_nan=False, description="blood_pressure: the top number (systolic). blood_sugar: mg/dL (or mmol/L with unit). spo2: percent. temperature: Celsius (or Fahrenheit with unit).")
    diastolic: float | None = Field(default=None, allow_inf_nan=False, description="blood_pressure only: the bottom number.")
    unit: str | None = Field(default=None, max_length=10, description="Optional. blood_sugar: mg/dL or mmol/L. temperature: C or F. Always stored and returned as mg/dL and Celsius.")
    context: Context | None = Field(default=None, description="blood_sugar only: fasting, after_meal or random.")
    recorded_at: datetime | None = Field(default=None, description="When it was measured, with a time zone. Default: now.")
    note: str | None = Field(default=None, max_length=200)
    client_id: UUID | None = Field(default=None, description="A random id for safe retry: the same id never saves twice.")


class VitalOut(BaseModel):
    reading_id: UUID
    dependent_id: UUID
    metric_type: Metric
    value: float
    diastolic: float | None = None
    unit: str = Field(description="mmHg, mg/dL, %, C or bpm")
    context: Context | None = None
    note: str | None = None
    source: Literal["manual", "wearable"]
    recorded_at: datetime
    created_at: datetime
    recorded_by: UUID | None = None
    recorded_by_name: str | None = None
    can_delete: bool
    already_saved: bool = False


class VitalList(BaseModel):
    items: list[VitalOut]
    total: int
    limit: int
    offset: int


class LatestVitals(BaseModel):
    dependent_id: UUID
    latest: dict[str, VitalOut | None] = Field(description="The newest reading of each metric, or null when there is none.")
