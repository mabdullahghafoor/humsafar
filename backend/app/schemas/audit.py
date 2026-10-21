"""Audit log reading (Task 6.6, FR-N3)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AuditActor(BaseModel):
    user_id: uuid.UUID
    full_name: str
    role: str


class AuditEntry(BaseModel):
    audit_id: uuid.UUID
    action: str = Field(description="Machine name, e.g. camera_view_started.")
    label: str = Field(description="Plain-English line to show on screen.")
    target_type: str
    target_id: uuid.UUID | None
    occurred_at: datetime
    actor: AuditActor


class AuditList(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int
