"""
Security & Surveillance module (SDS 8 / 9.2): camera_devices, camera_clips,
audit_logs.

Traces to: FR-K1, FR-K2, FR-N3.
"""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

CAMERA_END_REASONS = ("stopped", "expired", "unpaired", "permission_revoked")
CLIP_TRIGGERS = ("panic", "remote_alarm")
CLIP_STATUSES = ("requested", "stored", "missed")


class CameraDevice(Base):
    __tablename__ = "camera_devices"

    camera_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    stream_uri = Column(Text, nullable=False)  # Task 6.3: "rtc:<room id>" (the hosted RTC room the camera phone publishes into)
    paired_at = ts_col()
    name = Column(String(60), nullable=True)  # Task 6.3 (clarification 134)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)  # last heartbeat from the camera phone

    __table_args__ = (
        UniqueConstraint("dependent_id", name="uq_camera_devices_one_per_dependent"),
        CheckConstraint("char_length(btrim(stream_uri)) >= 1", name="stream_uri_not_blank"),
        CheckConstraint("name IS NULL OR char_length(btrim(name)) BETWEEN 1 AND 60", name="name_length"),
    )


class CameraSession(Base):
    """One Guardian watching one Dependent's camera (Task 6.3, FR-K1). Open while `ended_at` is NULL and `expires_at` is in the future."""

    __tablename__ = "camera_sessions"

    session_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    viewer_id = fk_col("users.user_id", index=True)
    started_at = ts_col()
    last_renewed_at = ts_col()
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    end_reason = Column(String(30), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("end_reason", CAMERA_END_REASONS), name="end_reason_valid"),
        CheckConstraint("(ended_at IS NULL) = (end_reason IS NULL)", name="ended_together"),
        CheckConstraint("expires_at > started_at", name="expiry_after_start"),
        Index("uq_camera_sessions_one_open", "dependent_id", "viewer_id", unique=True, postgresql_where=text("ended_at IS NULL")),
    )


class CameraClip(Base):
    """A short clip of an emergency (FR-K2). A row is created as a *request* when Panic Mode or the Remote Alarm starts; the camera
    phone records it and uploads it; `file_url` is then the storage key of the encrypted file. Never uploaded in time = `missed`."""

    __tablename__ = "camera_clips"

    clip_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    trigger_type = Column(String(30), nullable=False)
    file_url = Column(Text, nullable=True)
    captured_at = ts_col()  # when the event happened (the request time)
    event_id = Column(UUID(as_uuid=True), nullable=True)  # the panic event or the alarm this clip belongs to
    status = Column(String(15), nullable=False, server_default="requested")
    duration_s = Column(Integer, nullable=True)  # how long the phone was asked to record
    expires_at = Column(DateTime(timezone=True), nullable=True)  # the phone must upload before this
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    content_type = Column(String(30), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("trigger_type", CLIP_TRIGGERS), name="trigger_type_valid"),
        CheckConstraint(in_list("status", CLIP_STATUSES), name="status_valid"),
        CheckConstraint("(status = 'stored') = (file_url IS NOT NULL)", name="file_when_stored"),
        CheckConstraint("size_bytes IS NULL OR size_bytes > 0", name="size_positive"),
        Index("uq_camera_clips_one_per_event", "dependent_id", "trigger_type", "event_id", unique=True, postgresql_where=text("event_id IS NOT NULL")),
    )


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
