"""
Directory & Marketplace module (SDS 8 / 9.2): healthcare_organizations,
home_care_providers, booking_requests, activity_log.

Traces to: FR-I1, FR-I2, FR-J1, FR-J2.
"""

from sqlalchemy import Boolean, DateTime, CheckConstraint, Column, Float, Index, Numeric, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

ORG_TYPES = ("hospital", "clinic", "pharmacy", "ambulance", "emergency_service", "blood_bank", "laboratory")
CHARGE_UNITS = ("per_visit", "per_hour", "per_day", "per_month")
BOOKING_STATUSES = ("pending", "confirmed", "completed", "cancelled")
BOOKING_OPEN = ("pending", "confirmed")
ACTIVITY_TYPES = ("org_contact", "booking_request", "booking_confirmed", "booking_completed", "booking_cancelled")


class HealthcareOrganization(Base):
    __tablename__ = "healthcare_organizations"

    org_id = uuid_pk()
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # hospital, clinic, pharmacy ...
    phone = Column(String(20), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    # Task 6.1 (clarification 120): service details and housekeeping, added to the SDS table.
    address = Column(String(200), nullable=True)
    city = Column(String(80), nullable=False, server_default=text("'Nationwide'"))  # 'Nationwide' = a national number with no one location
    services = Column(String(500), nullable=True)  # short plain-text list of what they offer
    open_24h = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))  # hidden from the app when false
    is_sample = Column(Boolean, nullable=False, server_default=text("false"))  # demo entry, to be replaced by real data

    __table_args__ = (
        UniqueConstraint("name", "city", name="uq_healthcare_organizations_name_city"),
        CheckConstraint(in_list("type", ORG_TYPES), name="type_valid"),
        CheckConstraint("(lat IS NULL) = (lng IS NULL)", name="coordinates_together"),
        CheckConstraint("lat IS NULL OR (lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180)", name="coordinates_range"),
        CheckConstraint("char_length(btrim(name)) >= 1", name="name_not_blank"),
        Index("ix_healthcare_organizations_type", "type"),
    )


class HomeCareProvider(Base):
    __tablename__ = "home_care_providers"

    provider_id = uuid_pk()
    name = Column(String(200), nullable=False)
    specialization = Column(String(100), nullable=False)
    service_charge = Column(Numeric(10, 2), nullable=True)
    contact = Column(String(100), nullable=False)
    # Task 6.1 (clarification 120): profile details, added to the SDS table.
    bio = Column(String(1000), nullable=True)
    city = Column(String(80), nullable=False, server_default=text("'Not specified'"))
    experience_years = Column(SmallInteger, nullable=True)
    charge_unit = Column(String(20), nullable=False, server_default=text("'per_visit'"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_sample = Column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint("name", "contact", name="uq_home_care_providers_name_contact"),
        CheckConstraint("service_charge IS NULL OR service_charge >= 0", name="charge_not_negative"),
        CheckConstraint("experience_years IS NULL OR experience_years BETWEEN 0 AND 70", name="experience_range"),
        CheckConstraint(in_list("charge_unit", CHARGE_UNITS), name="charge_unit_valid"),
        CheckConstraint("char_length(btrim(name)) >= 1", name="name_not_blank"),
        Index("ix_home_care_providers_specialization", "specialization"),
    )


class BookingRequest(Base):
    __tablename__ = "booking_requests"

    request_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    provider_id = fk_col("home_care_providers.provider_id", index=True)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    requested_at = ts_col()
    # Task 6.2 (clarification 126): who asked, when the visit is wanted, a note, last change, safe retry.
    requested_by = fk_col("users.user_id", index=True)
    preferred_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(String(300), nullable=True)
    updated_at = ts_col()
    client_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("status", BOOKING_STATUSES), name="status_valid"),
        CheckConstraint("note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 300", name="note_length"),
        # one open request per Dependent and provider (no repeated requests for the same person)
        Index("uq_booking_requests_one_open", "dependent_id", "provider_id", unique=True, postgresql_where=text("status IN ('pending', 'confirmed')")),
        Index("uq_booking_requests_client", "requested_by", "client_id", unique=True, postgresql_where=text("client_id IS NOT NULL")),
    )


class ActivityLog(Base):
    """
    Shared table for the FR-I2/J2 merge (SDS 9.3). `reference_id` is polymorphic:
    it points at a healthcare_organizations contact event or a booking_requests
    row, selected by the `type` discriminator, so it carries NO foreign key.
    """

    __tablename__ = "activity_log"

    activity_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id")
    type = Column(String(30), nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    occurred_at = ts_col()
    # Task 6.2 (clarification 127): who did it and the name at that moment (history stays readable if an entry changes).
    initiated_by = fk_col("users.user_id", index=True)
    subject_name = Column(String(200), nullable=False, server_default=text("''"))

    __table_args__ = (
        Index("ix_activity_log_dependent_occurred", "dependent_id", "occurred_at"),
        CheckConstraint(in_list("type", ACTIVITY_TYPES), name="type_valid"),
    )
