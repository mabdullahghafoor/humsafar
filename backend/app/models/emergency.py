"""
Emergency & Escalation module (SDS 8 / 9.2): wellness_check_schedules,
wellness_check_responses, escalation_events, emergency_contacts.

Traces to: FR-D1, FR-D4, FR-D5, FR-R1.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

# SDS 9.4: "ordered enumeration reflecting the FR-D5 escalation sequence".
# Derived from SDS Fig. 12.2 / 15.1: Primary Guardian -> Secondary Guardian
# -> External Emergency Contact. Order in this tuple IS the escalation order.
ESCALATION_TIERS = ("primary", "secondary", "external_contact")


class WellnessCheckSchedule(Base):
    __tablename__ = "wellness_check_schedules"

    wc_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    time_window = Column(Time, nullable=False)  # e.g. 08:00 (one row per window)
    grace_period_min = Column(Integer, nullable=False, server_default=text("30"))
    # Task 3.4 (clarification 45): switching a check off keeps its history; created_at stops "late" first prompts.
    active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = ts_col()

    __table_args__ = (
        CheckConstraint("grace_period_min > 0", name="grace_positive"),
    )


class WellnessCheckResponse(Base):
    __tablename__ = "wellness_check_responses"

    response_id = uuid_pk()
    wc_id = fk_col("wellness_check_schedules.wc_id", index=True)
    prompted_at = ts_col()
    responded_at = Column(DateTime(timezone=True), nullable=True)
    # NOT NULL: safety-critical (SDS 9.4)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))

    __table_args__ = (
        # Task 3.4: one prompt per check per time, even if two processes run the job at once.
        UniqueConstraint("wc_id", "prompted_at", name="uq_wellness_prompt"),
    )


class EscalationEvent(Base):
    __tablename__ = "escalation_events"

    event_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id")
    trigger_type = Column(String(30), nullable=False)  # panic | missed_dose | wellness_check | fall ...
    tier = Column(String(30), nullable=False, server_default=text("'primary'"))
    status = Column(String(20), nullable=False, server_default=text("'open'"))
    created_at = ts_col()
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    # Task 3.3 (clarification 39): what the event is about, e.g. the missed dose. No foreign key: it points at
    # different tables depending on trigger_type. NULL for events about the Dependent as a whole.
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    # Task 3.5 (clarification 53): when the event moved to its current tier (the escalation timer starts here),
    # and who acknowledged it (a Guardian opened the alert), which stops the chain.
    tier_changed_at = ts_col()
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("tier", ESCALATION_TIERS), name="tier_valid"),
        Index("ix_escalation_events_dependent_status", "dependent_id", "status"),
        Index(
            "uq_open_event_per_reference",
            "reference_id",
            "trigger_type",
            unique=True,
            postgresql_where=text("status = 'open' AND reference_id IS NOT NULL"),
        ),
    )


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    contact_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
