"""
Shared column helpers for all Humsafar models.

Conventions (see SDS Section 9):
- Primary keys are UUIDs (SDS 11.2 examples use "uuid" identifiers, e.g. eventId).
- Every foreign key is NOT NULL unless explicitly documented otherwise (SDS 9.4).
- No ON DELETE CASCADE anywhere: SDS 9.4 disables direct cascading deletes.
  Deleting dependent-owned data happens only through the account-closure
  workflow (FR-O1), which deletes child rows explicitly in the right order.
- All timestamps are timezone-aware (UTC).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID


def uuid_pk() -> Column:
    """UUID primary key generated application-side."""
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk_col(
    target: str,
    *,
    nullable: bool = False,
    index: bool = False,
    unique: bool = False,
) -> Column:
    """UUID foreign key with RESTRICT on delete (no silent cascades)."""
    return Column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete="RESTRICT"),
        nullable=nullable,
        index=index,
        unique=unique,
    )


def ts_col(*, nullable: bool = False, default_now: bool = True) -> Column:
    """Timezone-aware timestamp. Defaults to now() on the database side."""
    return Column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )


def in_list(column: str, values) -> str:
    """Build the SQL text for a CHECK (column IN (...)) constraint."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
