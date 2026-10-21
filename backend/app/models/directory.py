"""
Directory & Marketplace module (SDS 8 / 9.2): healthcare_organizations,
home_care_providers, booking_requests, activity_log.

Traces to: FR-I1, FR-I2, FR-J1, FR-J2.
"""

from sqlalchemy import Column, Float, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models._common import fk_col, ts_col, uuid_pk


class HealthcareOrganization(Base):
    __tablename__ = "healthcare_organizations"

    org_id = uuid_pk()
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # hospital, clinic, pharmacy ...
    phone = Column(String(20), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)


class HomeCareProvider(Base):
    __tablename__ = "home_care_providers"

    provider_id = uuid_pk()
    name = Column(String(200), nullable=False)
    specialization = Column(String(100), nullable=False)
    service_charge = Column(Numeric(10, 2), nullable=True)
    contact = Column(String(100), nullable=False)


class BookingRequest(Base):
    __tablename__ = "booking_requests"

    request_id = uuid_pk()
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    provider_id = fk_col("home_care_providers.provider_id", index=True)
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    requested_at = ts_col()


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

    __table_args__ = (
        Index("ix_activity_log_dependent_occurred", "dependent_id", "occurred_at"),
    )
