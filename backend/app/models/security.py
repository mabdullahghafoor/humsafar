"""
Security & Surveillance module (SDS 8 / 9.2): camera_devices, camera_clips,
audit_logs.

Traces to: FR-K1, FR-K2, FR-N3.
"""

from sqlalchemy import Column, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models._common import fk_col, ts_col, uuid_pk


class CameraDevice(Base):
    __tablename__ = "camera_devices"

    camera_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    stream_uri = Column(Text, nullable=False)
    paired_at = ts_col()


class CameraClip(Base):
    __tablename__ = "camera_clips"

    clip_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    trigger_type = Column(String(30), nullable=False)
    file_url = Column(Text, nullable=False)
    captured_at = ts_col()


class AuditLog(Base):
    """Append-only record of sensitive actions (permission changes, camera views, record access)."""

    __tablename__ = "audit_logs"

    audit_id = uuid_pk()
    actor_id = fk_col("users.user_id", index=True)
    action = Column(String(60), nullable=False)
    target_type = Column(String(40), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=True)
    occurred_at = ts_col()

    __table_args__ = (
        Index("ix_audit_logs_target", "target_type", "target_id"),
    )
