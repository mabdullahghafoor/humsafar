"""
Identity & Access module (SDS 8 / 9.2): users, guardian_profiles,
dependent_profiles, guardian_dependent_links, permission_grants.

Traces to: FR-A1, FR-A2, FR-A3, FR-A4, FR-B1, FR-B2, FR-B4.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

USER_ROLES = ("guardian", "dependent")
GUARDIAN_ROLES = ("primary", "secondary")  # FR-A1: fixed at the account level
LINK_ROLES = ("primary", "secondary")  # SDS 9.4 check constraint

# FR-A4: governable modules ("at minimum"). Remote Alarm Override is deliberately
# NOT here: it is an inherent Primary Guardian privilege, never delegable.
# Kept as an application-level list (not a DB CHECK) because the SRS says
# "at minimum", so the list may grow without a schema migration.
PERMISSION_MODULES = (
    "live_location",
    "health_records",
    "communication",
    "emergency_alerts",
    "camera_viewing",
    "medication_management",
)


class User(Base):
    __tablename__ = "users"

    user_id = uuid_pk()
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(20), nullable=False, unique=True)
    # Added after the SDS freeze (clarification 27): the register screen asks for a name.
    full_name = Column(String(100), nullable=False, server_default="")
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    created_at = ts_col()

    guardian_profile = relationship(
        "GuardianProfile", back_populates="user", uselist=False
    )
    dependent_profile = relationship(
        "DependentProfile", back_populates="user", uselist=False
    )

    __table_args__ = (
        CheckConstraint(in_list("role", USER_ROLES), name="role_valid"),
    )


class GuardianProfile(Base):
    __tablename__ = "guardian_profiles"

    # Shared primary key: the PK is also a FK to users.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    cnic_verified = Column(Boolean, nullable=False, server_default=text("false"))
    phone_verified = Column(Boolean, nullable=False, server_default=text("false"))
    guardian_role = Column(String(20), nullable=False)

    user = relationship("User", back_populates="guardian_profile")
    links = relationship("GuardianDependentLink", back_populates="guardian")

    __table_args__ = (
        CheckConstraint(in_list("guardian_role", GUARDIAN_ROLES), name="guardian_role_valid"),
    )


class DependentProfile(Base):
    __tablename__ = "dependent_profiles"

    # Shared primary key: the PK is also a FK to users.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    # Nullable: the profile row exists from registration, CNIC arrives with KYC (Task 1.4).
    cnic = Column(String(15), nullable=True, unique=True)
    liveness_status = Column(String(20), nullable=False, server_default=text("'pending'"))
    dob = Column(Date, nullable=True)
    condition_notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="dependent_profile")
    links = relationship("GuardianDependentLink", back_populates="dependent")


class GuardianDependentLink(Base):
    __tablename__ = "guardian_dependent_links"

    link_id = uuid_pk()
    guardian_id = fk_col("guardian_profiles.user_id", index=True)
    dependent_id = fk_col("dependent_profiles.user_id", index=True)
    role = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # e.g. pending | active | revoked
    linked_at = ts_col()

    guardian = relationship("GuardianProfile", back_populates="links")
    dependent = relationship("DependentProfile", back_populates="links")
    permission_grants = relationship("PermissionGrant", back_populates="link")

    __table_args__ = (
        CheckConstraint(in_list("role", LINK_ROLES), name="role_valid"),
        # SDS 9.4: no duplicate linkage between the same guardian and dependent.
        UniqueConstraint("guardian_id", "dependent_id", name="uq_link_guardian_dependent"),
        # SDS 9.4 / FR-B2.2: exactly one Primary Guardian per Dependent,
        # enforced by a partial unique index.
        Index(
            "uq_one_primary_per_dependent",
            "dependent_id",
            unique=True,
            postgresql_where=text("role = 'primary'"),
        ),
    )


class PermissionGrant(Base):
    __tablename__ = "permission_grants"

    grant_id = uuid_pk()
    link_id = fk_col("guardian_dependent_links.link_id", index=True)
    module = Column(String(40), nullable=False)
    # Fail-safe default (SDS 6.3): access is denied until explicitly granted.
    granted = Column(Boolean, nullable=False, server_default=text("false"))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    link = relationship("GuardianDependentLink", back_populates="permission_grants")

    __table_args__ = (
        # SDS 9.3: one grant row per governable module per link.
        UniqueConstraint("link_id", "module", name="uq_grant_link_module"),
    )
