"""Schemas for the healthcare directory and the home-care provider directory (Task 6.1, FR-I1 and FR-J1)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

OrgType = Literal["hospital", "clinic", "pharmacy", "ambulance", "emergency_service", "blood_bank", "laboratory"]
ChargeUnit = Literal["per_visit", "per_hour", "per_day", "per_month"]


class OrganizationOut(BaseModel):
    org_id: UUID
    name: str
    type: OrgType
    phone: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str
    services: str | None = None
    open_24h: bool
    is_sample: bool = Field(description="true = a demo entry (made-up name and number), not real data yet.")
    distance_km: float | None = Field(default=None, description="Only when lat and lng were sent and the entry has a position. Entries without one (national numbers) have null.")


class OrganizationList(BaseModel):
    items: list[OrganizationOut]
    total: int
    limit: int
    offset: int


class TypeCount(BaseModel):
    type: str
    count: int


class OrganizationTypes(BaseModel):
    types: list[TypeCount]


class ProviderOut(BaseModel):
    provider_id: UUID
    name: str
    specialization: str
    service_charge: float | None = Field(default=None, description="Amount in PKR (a number), for the unit in charge_unit.")
    charge_unit: ChargeUnit
    contact: str
    bio: str | None = None
    city: str
    experience_years: int | None = None
    is_sample: bool


class ProviderList(BaseModel):
    items: list[ProviderOut]
    total: int
    limit: int
    offset: int


class SpecializationCount(BaseModel):
    specialization: str
    count: int


class Specializations(BaseModel):
    specializations: list[SpecializationCount]
