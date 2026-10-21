"""healthcare directory + home-care provider directory: details, checks, seed data (Task 6.1)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-21 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.seed.directory_data import ORGANIZATIONS, PROVIDERS

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG_TYPES = ("hospital", "clinic", "pharmacy", "ambulance", "emergency_service", "blood_bank", "laboratory")
CHARGE_UNITS = ("per_visit", "per_hour", "per_day", "per_month")


def _in(col, values):
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # healthcare_organizations
    op.add_column("healthcare_organizations", sa.Column("address", sa.String(200), nullable=True))
    op.add_column("healthcare_organizations", sa.Column("city", sa.String(80), nullable=False, server_default=sa.text("'Nationwide'")))
    op.add_column("healthcare_organizations", sa.Column("services", sa.String(500), nullable=True))
    op.add_column("healthcare_organizations", sa.Column("open_24h", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("healthcare_organizations", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("healthcare_organizations", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_unique_constraint("uq_healthcare_organizations_name_city", "healthcare_organizations", ["name", "city"])
    op.create_check_constraint(op.f("ck_healthcare_organizations_type_valid"), "healthcare_organizations", _in("type", ORG_TYPES))
    op.create_check_constraint(op.f("ck_healthcare_organizations_coordinates_together"), "healthcare_organizations", "(lat IS NULL) = (lng IS NULL)")
    op.create_check_constraint(
        op.f("ck_healthcare_organizations_coordinates_range"), "healthcare_organizations",
        "lat IS NULL OR (lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180)",
    )
    op.create_check_constraint(op.f("ck_healthcare_organizations_name_not_blank"), "healthcare_organizations", "char_length(btrim(name)) >= 1")
    op.create_index(op.f("ix_healthcare_organizations_type"), "healthcare_organizations", ["type"])

    # home_care_providers
    op.add_column("home_care_providers", sa.Column("bio", sa.String(1000), nullable=True))
    op.add_column("home_care_providers", sa.Column("city", sa.String(80), nullable=False, server_default=sa.text("'Not specified'")))
    op.add_column("home_care_providers", sa.Column("experience_years", sa.SmallInteger(), nullable=True))
    op.add_column("home_care_providers", sa.Column("charge_unit", sa.String(20), nullable=False, server_default=sa.text("'per_visit'")))
    op.add_column("home_care_providers", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("home_care_providers", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_unique_constraint("uq_home_care_providers_name_contact", "home_care_providers", ["name", "contact"])
    op.create_check_constraint(op.f("ck_home_care_providers_charge_not_negative"), "home_care_providers", "service_charge IS NULL OR service_charge >= 0")
    op.create_check_constraint(op.f("ck_home_care_providers_experience_range"), "home_care_providers", "experience_years IS NULL OR experience_years BETWEEN 0 AND 70")
    op.create_check_constraint(op.f("ck_home_care_providers_charge_unit_valid"), "home_care_providers", _in("charge_unit", CHARGE_UNITS))
    op.create_check_constraint(op.f("ck_home_care_providers_name_not_blank"), "home_care_providers", "char_length(btrim(name)) >= 1")
    op.create_index(op.f("ix_home_care_providers_specialization"), "home_care_providers", ["specialization"])

    # Starting content (safe to run again: existing rows are left alone).
    conn = op.get_bind()
    for name, typ, phone, lat, lng, address, city, services, open_24h, is_sample in ORGANIZATIONS:
        conn.execute(
            sa.text(
                "INSERT INTO healthcare_organizations (name, type, phone, lat, lng, address, city, services, open_24h, is_sample) "
                "VALUES (:name, :type, :phone, :lat, :lng, :address, :city, :services, :open_24h, :is_sample) "
                "ON CONFLICT ON CONSTRAINT uq_healthcare_organizations_name_city DO NOTHING"
            ),
            dict(name=name, type=typ, phone=phone, lat=lat, lng=lng, address=address, city=city, services=services, open_24h=open_24h, is_sample=is_sample),
        )
    for name, spec, charge, unit, contact, bio, city, years, is_sample in PROVIDERS:
        conn.execute(
            sa.text(
                "INSERT INTO home_care_providers (name, specialization, service_charge, charge_unit, contact, bio, city, experience_years, is_sample) "
                "VALUES (:name, :spec, :charge, :unit, :contact, :bio, :city, :years, :is_sample) "
                "ON CONFLICT ON CONSTRAINT uq_home_care_providers_name_contact DO NOTHING"
            ),
            dict(name=name, spec=spec, charge=charge, unit=unit, contact=contact, bio=bio, city=city, years=years, is_sample=is_sample),
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Remove only the starting content this migration added, and only what nothing else points at.
    for name, *_rest in PROVIDERS:
        conn.execute(
            sa.text(
                "DELETE FROM home_care_providers p WHERE p.name = :n AND p.is_sample "
                "AND NOT EXISTS (SELECT 1 FROM booking_requests b WHERE b.provider_id = p.provider_id)"
            ),
            {"n": name},
        )
    for name, *_rest in ORGANIZATIONS:
        conn.execute(sa.text("DELETE FROM healthcare_organizations WHERE name = :n"), {"n": name})

    op.drop_index(op.f("ix_home_care_providers_specialization"), table_name="home_care_providers")
    for c in ("name_not_blank", "charge_unit_valid", "experience_range", "charge_not_negative"):
        op.drop_constraint(op.f(f"ck_home_care_providers_{c}"), "home_care_providers", type_="check")
    op.drop_constraint("uq_home_care_providers_name_contact", "home_care_providers", type_="unique")
    for col in ("is_sample", "is_active", "charge_unit", "experience_years", "city", "bio"):
        op.drop_column("home_care_providers", col)

    op.drop_index(op.f("ix_healthcare_organizations_type"), table_name="healthcare_organizations")
    for c in ("name_not_blank", "coordinates_range", "coordinates_together", "type_valid"):
        op.drop_constraint(op.f(f"ck_healthcare_organizations_{c}"), "healthcare_organizations", type_="check")
    op.drop_constraint("uq_healthcare_organizations_name_city", "healthcare_organizations", type_="unique")
    for col in ("is_sample", "is_active", "open_24h", "services", "city", "address"):
        op.drop_column("healthcare_organizations", col)
