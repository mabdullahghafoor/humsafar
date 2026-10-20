"""Schemas for the appointment tracker (Task 5.1, FR-G4)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator


def _clean(v: str | None) -> str | None:
    if isinstance(v, str) and "\x00" in v:
        raise ValueError("This text contains a character that is not allowed.")  # the database cannot store a NUL character
    return v.strip() if isinstance(v, str) else v


class AppointmentIn(BaseModel):
    provider_name: str = Field(min_length=1, max_length=150, description="The doctor, clinic or hospital.")
    scheduled_at: AwareDatetime = Field(description="When, with a time zone, e.g. 2026-11-03T10:30:00+05:00. Must be in the future.")
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("provider_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _clean(v)
        if not v:
            raise ValueError("The name is empty.")
        return v

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        v = _clean(v)
        return v or None


class AppointmentUpdate(BaseModel):
    provider_name: str | None = Field(default=None, min_length=1, max_length=150)
    scheduled_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=2000, description="Send null or empty text to clear it.")

    @model_validator(mode="after")
    def _check(self) -> "AppointmentUpdate":
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        for f in ("provider_name", "scheduled_at"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be empty.")
        if self.provider_name is not None:
            self.provider_name = _clean(self.provider_name)
            if not self.provider_name:
                raise ValueError("The name is empty.")
        if self.notes is not None:
            self.notes = _clean(self.notes) or None
        return self


class AppointmentOut(BaseModel):
    appointment_id: UUID
    dependent_id: UUID
    provider_name: str
    scheduled_at: datetime
    notes: str | None = None
    status: Literal["scheduled", "cancelled"]
    created_by: UUID
    created_by_name: str | None = None
    created_at: datetime
    is_upcoming: bool = Field(description="Scheduled and still in the future.")


class AppointmentList(BaseModel):
    items: list[AppointmentOut] = Field(description="`upcoming`: soonest first. `past` and `all`: latest first.")
    total: int
    limit: int
    offset: int
