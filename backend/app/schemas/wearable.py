"""Schemas for the wearable band (Task 5.4, FR-H2)."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.vitals import VitalOut

BandMetric = Literal["heart_rate", "spo2", "temperature"]
ADDRESS = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


class BandPairIn(BaseModel):
    ble_address: str = Field(max_length=17, description="The band's Bluetooth address, for example C4:5B:BE:12:34:56 (a dash instead of a colon, and small letters, are fine).")
    name: str | None = Field(default=None, max_length=60, description="Optional label, for example the name the band advertises.")

    @field_validator("ble_address")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip().upper().replace("-", ":")
        if not ADDRESS.match(v):
            raise ValueError("ble_address must look like AA:BB:CC:DD:EE:FF")
        return v


class BandOut(BaseModel):
    device_id: UUID
    dependent_id: UUID
    ble_address: str
    name: str | None = None
    paired_at: datetime
    last_sync_at: datetime | None = None


class BandReadingIn(BaseModel):
    metric_type: BandMetric
    value: float = Field(allow_inf_nan=False, description="heart_rate: beats per minute. spo2: percent. temperature: degrees Celsius.")
    recorded_at: datetime = Field(description="When the band measured it, with a time zone.")


class SyncIn(BaseModel):
    readings: list[BandReadingIn] = Field(min_length=1, description="Up to 500 readings (WEARABLE_MAX_BATCH).")


class Rejected(BaseModel):
    index: int = Field(description="Position in the `readings` list you sent, starting at 0.")
    reason: str


class SyncOut(BaseModel):
    received: int
    stored: int
    duplicates: int = Field(description="Already stored (a retried batch): skipped, not an error.")
    rejected: list[Rejected]
    last_sync_at: datetime | None = None


class MockIn(BaseModel):
    count: int = Field(default=30, ge=1, le=200)
    interval_s: int = Field(default=60, ge=10, le=3600, description="Seconds between the fake readings, newest ends now.")


class BandStatus(BaseModel):
    dependent_id: UUID
    status: Literal["not_paired", "waiting_for_first_data", "receiving", "no_data"]
    device: BandOut | None = None
    last_data_at: datetime | None = Field(default=None, description="Server time of the last accepted sync (or null).")
    seconds_since_data: int | None = None
    no_data_alert_open: bool = False
    no_data_alert_since: datetime | None = None
    no_data_after_s: int
    latest_heart_rate: VitalOut | None = None
