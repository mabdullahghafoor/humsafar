"""
Medication & Records module (SDS 8 / 9.2): medication_schedules,
medication_confirmations, medical_records, vital_readings, appointments,
wearable_devices.

Traces to: FR-F1, FR-D1, FR-G1..G4, FR-H1, FR-H2.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

VITAL_SOURCES = ("manual", "wearable")


class MedicationSchedule(Base):
    __tablename__ = "medication_schedules"

    schedule_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    drug_name = Column(String(150), nullable=False)
    dosage = Column(String(100), nullable=False)
    time_of_day = Column(Time, nullable=False)  # one row per dose time
    frequency = Column(String(50), nullable=False)  # e.g. daily, weekly
    created_by = fk_col("users.user_id")
    # Task 3.2 (clarification 33): a removed schedule is switched off, not deleted, so the dose history stays.
    active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = ts_col()


class MedicationConfirmation(Base):
    __tablename__ = "medication_confirmations"

    confirmation_id = uuid_pk()
    schedule_id = fk_col("medication_schedules.schedule_id", index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    # NOT NULL: safety-critical (SDS 9.4)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))

    __table_args__ = (
        # One confirmation row per scheduled dose instance.
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_confirmation_schedule_dose"),
    )


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    record_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    type = Column(String(50), nullable=False)
    file_url = Column(Text, nullable=False)
    uploaded_by = fk_col("users.user_id")
    uploaded_at = ts_col()


class VitalReading(Base):
    __tablename__ = "vital_readings"

    reading_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id")
    metric_type = Column(String(30), nullable=False)  # heart_rate, steps, bp, ...
    value = Column(Float, nullable=False)
    # Nullable: wearable-sourced readings have no human recorder.
    recorded_by = fk_col("users.user_id", nullable=True)
    recorded_at = ts_col()
    source = Column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint(in_list("source", VITAL_SOURCES), name="source_valid"),
        Index(
            "ix_vital_readings_dependent_metric_recorded",
            "dependent_id",
            "metric_type",
            "recorded_at",
        ),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    provider_name = Column(String(150), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)


class WearableDevice(Base):
    __tablename__ = "wearable_devices"

    device_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    ble_address = Column(String(17), nullable=False)  # AA:BB:CC:DD:EE:FF
    paired_at = ts_col()
    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("dependent_id", "ble_address", name="uq_wearable_dependent_address"),
    )
