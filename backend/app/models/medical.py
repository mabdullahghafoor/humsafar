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
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

VITAL_SOURCES = ("manual", "wearable")
VITAL_METRICS = ("blood_pressure", "blood_sugar", "spo2", "temperature", "heart_rate")  # the first four are typed in (FR-H1); heart_rate comes from the band (5.4)
MANUAL_METRICS = ("blood_pressure", "blood_sugar", "spo2", "temperature")
BAND_METRICS = ("heart_rate", "spo2", "temperature")  # what the wearable band may send (Task 5.4)
SUGAR_CONTEXTS = ("fasting", "after_meal", "random")
RECORD_CATEGORIES = ("prescription", "lab_report", "xray", "other")  # FR-G1 (the SDS column is `type`)
APPOINTMENT_STATUSES = ("scheduled", "cancelled")
SHARE_SCOPES = ("complete", "year", "month")


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
    # Task 3.3 (clarification 40): a Guardian can give more time; this is then the new deadline.
    extended_until = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One confirmation row per scheduled dose instance.
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_confirmation_schedule_dose"),
    )


class MedicalRecord(Base):
    """
    One entry in the Medical Vault (Task 5.1, FR-G1). It can hold an uploaded file (PDF / JPEG / PNG, stored
    encrypted, see records_service), a typed note, or both. `type` is the category (SDS column name).
    """

    __tablename__ = "medical_records"

    record_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    type = Column(String(50), nullable=False)
    # Task 5.1 (clarification 91): nullable now, because a record may be a typed note without a file.
    file_url = Column(Text, nullable=True)
    uploaded_by = fk_col("users.user_id")
    uploaded_at = ts_col()
    title = Column(String(150), nullable=False)
    notes = Column(Text, nullable=True)
    record_date = Column(Date, nullable=False)  # the date of the document / visit; year and month exports use it
    file_name = Column(String(150), nullable=True)  # the name shown on download (cleaned)
    content_type = Column(String(50), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    client_id = Column(UUID(as_uuid=True), nullable=True)  # safe retry of an upload

    __table_args__ = (
        CheckConstraint(in_list("type", RECORD_CATEGORIES), name="type_valid"),
        CheckConstraint("file_url IS NOT NULL OR (notes IS NOT NULL AND char_length(btrim(notes)) > 0)", name="has_content"),
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 150", name="title_length"),
        CheckConstraint("notes IS NULL OR char_length(notes) <= 5000", name="notes_length"),
        CheckConstraint("file_url IS NOT NULL OR (content_type IS NULL AND size_bytes IS NULL AND file_name IS NULL)", name="file_meta"),
        CheckConstraint("size_bytes IS NULL OR size_bytes > 0", name="size_positive"),
        Index("ix_medical_records_dependent_date", "dependent_id", "record_date"),
        Index("uq_medical_records_uploader_client", "uploaded_by", "client_id", unique=True, postgresql_where=text("client_id IS NOT NULL")),
    )


class RecordShare(Base):
    """A doctor-shareable read-only link (Task 5.1, FR-G3). Only a hash of the secret token is stored."""

    __tablename__ = "record_shares"

    share_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    created_by = fk_col("users.user_id")
    token_hash = Column(String(64), nullable=False, unique=True)
    scope = Column(String(10), nullable=False)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)
    categories = Column(ARRAY(String(50)), nullable=False)  # what the link shows, fixed when it was made
    include_vitals = Column(Boolean, nullable=False, server_default=text("false"))  # Task 5.3: also show the vitals
    created_at = ts_col()
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    open_count = Column(Integer, nullable=False, server_default=text("0"))
    last_opened_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("scope", SHARE_SCOPES), name="scope_valid"),
        CheckConstraint(
            "(scope = 'complete' AND year IS NULL AND month IS NULL) "
            "OR (scope = 'year' AND year IS NOT NULL AND month IS NULL) "
            "OR (scope = 'month' AND year IS NOT NULL AND month IS NOT NULL)",
            name="scope_period",
        ),
        CheckConstraint("month IS NULL OR month BETWEEN 1 AND 12", name="month_range"),
        CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2200", name="year_range"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("cardinality(categories) >= 1", name="has_categories"),
    )


class RecordCategoryRestriction(Base):
    """Task 5.2 (FR-G2): this Secondary Guardian may NOT see this record category for this Dependent.

    A row means "hidden". No row means the Secondary sees the category, as long as the `health_records` module
    is granted (that grant stays the first gate). Stored per link, so it is independent per Dependent (FR-B4).
    """

    __tablename__ = "record_category_restrictions"

    restriction_id = uuid_pk()
    link_id = fk_col("guardian_dependent_links.link_id", index=True)
    category = Column(String(50), nullable=False)
    created_at = ts_col()

    __table_args__ = (
        UniqueConstraint("link_id", "category", name="uq_restriction_link_category"),
        CheckConstraint(in_list("category", RECORD_CATEGORIES), name="category_valid"),
    )


class VitalReading(Base):
    """One health reading. Units are fixed: blood_pressure mmHg (value = systolic, diastolic), blood_sugar mg/dL, spo2 %,
    temperature degrees Celsius, heart_rate beats per minute (Task 5.3, FR-H1)."""

    __tablename__ = "vital_readings"

    reading_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id")
    metric_type = Column(String(30), nullable=False)
    value = Column(Float, nullable=False)
    diastolic = Column(Float, nullable=True)  # blood_pressure only
    context = Column(String(20), nullable=True)  # blood_sugar only: fasting / after_meal / random
    note = Column(Text, nullable=True)
    # Nullable: wearable-sourced readings have no human recorder.
    recorded_by = fk_col("users.user_id", nullable=True)
    recorded_at = ts_col()  # when it was measured
    created_at = ts_col()  # when it was saved
    source = Column(String(20), nullable=False)
    client_id = Column(UUID(as_uuid=True), nullable=True)  # safe retry (one per recorder)

    __table_args__ = (
        CheckConstraint(in_list("source", VITAL_SOURCES), name="source_valid"),
        CheckConstraint(in_list("metric_type", VITAL_METRICS), name="metric_valid"),
        CheckConstraint(
            "(source = 'manual' AND metric_type IN ('blood_pressure', 'blood_sugar', 'spo2', 'temperature')) "
            "OR (source = 'wearable' AND metric_type IN ('heart_rate', 'spo2', 'temperature'))",
            name="source_metric_valid",
        ),
        CheckConstraint("(metric_type = 'blood_pressure') = (diastolic IS NOT NULL)", name="diastolic_for_bp"),
        CheckConstraint("context IS NULL OR (metric_type = 'blood_sugar' AND context IN ('fasting', 'after_meal', 'random'))", name="context_for_sugar"),
        CheckConstraint("note IS NULL OR char_length(note) <= 200", name="note_length"),
        Index(
            "ix_vital_readings_dependent_metric_recorded",
            "dependent_id",
            "metric_type",
            "recorded_at",
        ),
        Index("uq_vital_readings_recorder_client", "recorded_by", "client_id", unique=True, postgresql_where=text("client_id IS NOT NULL")),
        # Task 5.4: the same band sample sent twice (a retried batch) is stored once.
        Index("uq_vital_readings_wearable_sample", "dependent_id", "metric_type", "recorded_at", unique=True, postgresql_where=text("source = 'wearable'")),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    provider_name = Column(String(150), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
    # Task 5.1 (clarification 97): who made it, whether it was cancelled, and when its time was last set
    # (so a reminder is not sent for a time that has already passed when the appointment was made).
    created_by = fk_col("users.user_id")
    status = Column(String(15), nullable=False, server_default=text("'scheduled'"))
    time_set_at = ts_col()
    created_at = ts_col()

    __table_args__ = (
        CheckConstraint(in_list("status", APPOINTMENT_STATUSES), name="status_valid"),
        CheckConstraint("char_length(btrim(provider_name)) BETWEEN 1 AND 150", name="provider_length"),
        CheckConstraint("notes IS NULL OR char_length(notes) <= 2000", name="notes_length"),
        Index("ix_appointments_dependent_time", "dependent_id", "scheduled_at"),
        Index("ix_appointments_open_time", "scheduled_at", postgresql_where=text("status = 'scheduled'")),
    )


class WearableDevice(Base):
    __tablename__ = "wearable_devices"

    device_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    ble_address = Column(String(17), nullable=False)  # AA:BB:CC:DD:EE:FF
    paired_at = ts_col()
    last_sync_at = Column(DateTime(timezone=True), nullable=True)  # server time of the last accepted sync (Task 5.4)
    name = Column(String(60), nullable=True)

    __table_args__ = (
        UniqueConstraint("dependent_id", "ble_address", name="uq_wearable_dependent_address"),
        UniqueConstraint("dependent_id", name="uq_wearable_one_per_dependent"),  # one band per Dependent (clarification 113)
        CheckConstraint("ble_address ~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'", name="address_format"),
        CheckConstraint("name IS NULL OR char_length(btrim(name)) BETWEEN 1 AND 60", name="name_length"),
    )
