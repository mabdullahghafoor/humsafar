"""Schemas for the Medical Vault (Task 5.1, FR-G1, FR-G3)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Category = Literal["prescription", "lab_report", "xray", "other"]
Scope = Literal["complete", "year", "month"]


class RecordOut(BaseModel):
    record_id: UUID
    dependent_id: UUID
    category: Category
    title: str
    notes: str | None = None
    record_date: date = Field(description="The date of the document or visit. Year and month exports use this date.")
    has_file: bool
    file_name: str | None = None
    content_type: str | None = Field(default=None, description="application/pdf, image/jpeg or image/png.")
    size_bytes: int | None = None
    file_path: str | None = Field(default=None, description="Download the file here (send the login token). Null if the record has no file.")
    uploaded_by: UUID
    uploaded_by_name: str | None = None
    uploaded_at: datetime
    can_modify: bool = Field(description="True if the person asking may edit or delete this record (its uploader, or the Primary Guardian).")
    already_saved: bool = Field(default=False, description="Only on POST: true if this `client_id` was saved before (nothing new was saved).")


class RecordList(BaseModel):
    items: list[RecordOut] = Field(description="Newest record date first.")
    total: int = Field(description="How many records match (all pages).")
    limit: int
    offset: int


class RecordUpdate(BaseModel):
    """Only the fields you send are changed. The file itself cannot be replaced: delete the record and add a new one."""

    category: Category | None = None
    title: str | None = Field(default=None, min_length=1, max_length=150)
    notes: str | None = Field(default=None, max_length=5000, description="Send null or empty text to clear the note (not possible if the record has no file).")
    record_date: date | None = None

    @model_validator(mode="after")
    def _something(self) -> "RecordUpdate":
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        for f in ("category", "title", "record_date"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be empty.")
        return self


class ShareIn(BaseModel):
    scope: Scope = Field(default="complete", description="What the link shows: everything, one year, or one month.")
    year: int | None = Field(default=None, ge=1900, le=2200)
    month: int | None = Field(default=None, ge=1, le=12)
    hours: int | None = Field(default=None, ge=1, description="How long the link works. Default 72, longest 720 (30 days).")
    categories: list[Category] | None = Field(default=None, min_length=1, description="Only these categories. Default: all you may see.")

    @model_validator(mode="after")
    def _period(self) -> "ShareIn":
        check_period(self.scope, self.year, self.month)
        return self


def check_period(scope: str, year: int | None, month: int | None) -> None:
    if scope == "complete" and (year is not None or month is not None):
        raise ValueError("For the complete history, do not send year or month.")
    if scope == "year" and (year is None or month is not None):
        raise ValueError("For a year export, send year (and no month).")
    if scope == "month" and (year is None or month is None):
        raise ValueError("For a month export, send year and month.")


class ShareOut(BaseModel):
    share_id: UUID
    dependent_id: UUID
    created_by: UUID
    scope: Scope
    year: int | None = None
    month: int | None = None
    categories: list[Category]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    status: Literal["active", "expired", "revoked"]
    open_count: int
    last_opened_at: datetime | None = None


class ShareCreated(ShareOut):
    token: str = Field(description="The secret. Shown ONLY now; the server keeps just a hash. Give it to the doctor inside the link.")
    url: str = Field(description="The read-only link (a PDF). A path like /shared/records/<token>, or a full address when PUBLIC_BASE_URL is set.")


class ShareList(BaseModel):
    items: list[ShareOut]


# --- Task 5.2 (FR-G2): which record categories a Secondary Guardian may see


class SetRecordAccessRequest(BaseModel):
    guardian_id: UUID = Field(description="The Secondary Guardian.")
    visible: bool = Field(description="true = may see this category, false = hidden from them.")


class RecordAccessOut(BaseModel):
    dependent_id: UUID
    guardian_id: UUID
    category: Category
    visible: bool
    visible_categories: list[Category]


class SecondaryRecordAccess(BaseModel):
    guardian_id: UUID
    email: str | None = None
    phone: str | None = None
    health_records_granted: bool = Field(description="The `health_records` module (Task 1.6). false = they see no records at all.")
    categories: dict[str, bool] = Field(description="Per category: true = visible, false = hidden. Only counts when the module is granted.")


class RecordAccessDashboard(BaseModel):
    dependent_id: UUID
    categories: list[Category]
    secondaries: list[SecondaryRecordAccess]


class MyRecordAccess(BaseModel):
    dependent_id: UUID
    categories: dict[str, bool]
    visible_categories: list[Category]
