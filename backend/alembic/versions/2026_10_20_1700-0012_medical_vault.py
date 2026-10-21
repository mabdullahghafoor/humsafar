"""medical vault: record details, doctor share links, appointment status (Task 5.1)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- medical_records
    op.add_column("medical_records", sa.Column("title", sa.String(150), nullable=False, server_default=sa.text("'Record'")))
    op.add_column("medical_records", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("medical_records", sa.Column("record_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")))
    op.add_column("medical_records", sa.Column("file_name", sa.String(150), nullable=True))
    op.add_column("medical_records", sa.Column("content_type", sa.String(50), nullable=True))
    op.add_column("medical_records", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("medical_records", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.alter_column("medical_records", "title", server_default=None)  # the default only filled rows that already existed
    op.alter_column("medical_records", "record_date", server_default=None)
    op.alter_column("medical_records", "file_url", existing_type=sa.Text(), nullable=True)
    op.execute("UPDATE medical_records SET type = 'other' WHERE type NOT IN ('prescription', 'lab_report', 'xray', 'other')")
    op.create_check_constraint(op.f("ck_medical_records_type_valid"), "medical_records", "type IN ('prescription', 'lab_report', 'xray', 'other')")
    op.create_check_constraint(op.f("ck_medical_records_has_content"), "medical_records", "file_url IS NOT NULL OR (notes IS NOT NULL AND char_length(btrim(notes)) > 0)")
    op.create_check_constraint(op.f("ck_medical_records_title_length"), "medical_records", "char_length(btrim(title)) BETWEEN 1 AND 150")
    op.create_check_constraint(op.f("ck_medical_records_notes_length"), "medical_records", "notes IS NULL OR char_length(notes) <= 5000")
    op.create_check_constraint(op.f("ck_medical_records_file_meta"), "medical_records", "file_url IS NOT NULL OR (content_type IS NULL AND size_bytes IS NULL AND file_name IS NULL)")
    op.create_check_constraint(op.f("ck_medical_records_size_positive"), "medical_records", "size_bytes IS NULL OR size_bytes > 0")
    op.create_index("ix_medical_records_dependent_date", "medical_records", ["dependent_id", "record_date"])
    op.create_index("uq_medical_records_uploader_client", "medical_records", ["uploaded_by", "client_id"], unique=True, postgresql_where=sa.text("client_id IS NOT NULL"))

    # --- record_shares
    op.create_table(
        "record_shares",
        sa.Column("share_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dependent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("categories", postgresql.ARRAY(sa.String(50)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('complete', 'year', 'month')", name=op.f("ck_record_shares_scope_valid")),
        sa.CheckConstraint(
            "(scope = 'complete' AND year IS NULL AND month IS NULL) "
            "OR (scope = 'year' AND year IS NOT NULL AND month IS NULL) "
            "OR (scope = 'month' AND year IS NOT NULL AND month IS NOT NULL)",
            name=op.f("ck_record_shares_scope_period"),
        ),
        sa.CheckConstraint("month IS NULL OR month BETWEEN 1 AND 12", name=op.f("ck_record_shares_month_range")),
        sa.CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2200", name=op.f("ck_record_shares_year_range")),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_record_shares_expires_after_created")),
        sa.CheckConstraint("cardinality(categories) >= 1", name=op.f("ck_record_shares_has_categories")),
        sa.ForeignKeyConstraint(["dependent_id"], ["dependent_profiles.user_id"], name=op.f("fk_record_shares_dependent_id_dependent_profiles"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], name=op.f("fk_record_shares_created_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("share_id", name=op.f("pk_record_shares")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_record_shares_token_hash")),
    )
    op.create_index(op.f("ix_record_shares_dependent_id"), "record_shares", ["dependent_id"])

    # --- appointments
    op.add_column("appointments", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("appointments", sa.Column("status", sa.String(15), nullable=False, server_default=sa.text("'scheduled'")))
    op.add_column("appointments", sa.Column("time_set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("appointments", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.execute("UPDATE appointments SET created_by = dependent_id WHERE created_by IS NULL")  # no endpoint existed before, so normally no rows
    op.alter_column("appointments", "created_by", nullable=False)
    op.create_foreign_key(op.f("fk_appointments_created_by_users"), "appointments", "users", ["created_by"], ["user_id"], ondelete="RESTRICT")
    op.create_check_constraint(op.f("ck_appointments_status_valid"), "appointments", "status IN ('scheduled', 'cancelled')")
    op.create_check_constraint(op.f("ck_appointments_provider_length"), "appointments", "char_length(btrim(provider_name)) BETWEEN 1 AND 150")
    op.create_check_constraint(op.f("ck_appointments_notes_length"), "appointments", "notes IS NULL OR char_length(notes) <= 2000")
    op.create_index("ix_appointments_dependent_time", "appointments", ["dependent_id", "scheduled_at"])
    op.create_index("ix_appointments_open_time", "appointments", ["scheduled_at"], postgresql_where=sa.text("status = 'scheduled'"))


def downgrade() -> None:
    op.drop_index("ix_appointments_open_time", table_name="appointments")
    op.drop_index("ix_appointments_dependent_time", table_name="appointments")
    for c in ("notes_length", "provider_length", "status_valid"):
        op.drop_constraint(op.f(f"ck_appointments_{c}"), "appointments", type_="check")
    op.drop_constraint(op.f("fk_appointments_created_by_users"), "appointments", type_="foreignkey")
    for c in ("created_at", "time_set_at", "status", "created_by"):
        op.drop_column("appointments", c)

    op.drop_index(op.f("ix_record_shares_dependent_id"), table_name="record_shares")
    op.drop_table("record_shares")

    op.drop_index("uq_medical_records_uploader_client", table_name="medical_records")
    op.drop_index("ix_medical_records_dependent_date", table_name="medical_records")
    for c in ("size_positive", "file_meta", "notes_length", "title_length", "has_content", "type_valid"):
        op.drop_constraint(op.f(f"ck_medical_records_{c}"), "medical_records", type_="check")
    op.execute("UPDATE medical_records SET file_url = '' WHERE file_url IS NULL")  # the old column was NOT NULL
    op.alter_column("medical_records", "file_url", existing_type=sa.Text(), nullable=False)
    for c in ("client_id", "size_bytes", "content_type", "file_name", "record_date", "notes", "title"):
        op.drop_column("medical_records", c)
