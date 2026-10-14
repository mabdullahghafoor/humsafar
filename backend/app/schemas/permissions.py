"""Request/response schemas for the permission dashboard (Task 1.6, FR-A4)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SetPermissionRequest(BaseModel):
    guardian_id: UUID  # the Secondary Guardian whose access is being changed
    granted: bool


class PermissionOut(BaseModel):
    dependent_id: UUID
    guardian_id: UUID
    module: str
    granted: bool
    updated_at: datetime | None  # None = never configured (default deny)


class SecondaryPermissions(BaseModel):
    guardian_id: UUID
    email: str
    phone: str
    modules: dict[str, bool]  # every governable module; false unless explicitly granted


class DashboardOut(BaseModel):
    dependent_id: UUID
    modules: list[str]  # the governable module list
    secondaries: list[SecondaryPermissions]


class MyPermissionsOut(BaseModel):
    dependent_id: UUID
    guardian_role: str  # 'primary' or 'secondary'
    modules: dict[str, bool]  # a Primary has every module; remote alarm is never listed here
