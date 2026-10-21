"""booking requests + shared activity log: who, when, note, status rules, safe retry (Task 6.2)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("booking_requests", sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("booking_requests", sa.Column("preferred_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("booking_requests", sa.Column("note", sa.String(300), nullable=True))
    op.add_column("booking_requests", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("booking_requests", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(op.f("fk_booking_requests_requested_by_users"), "booking_requests", "users", ["requested_by"], ["user_id"], ondelete="RESTRICT")
    op.create_index(op.f("ix_booking_requests_requested_by"), "booking_requests", ["requested_by"])
    op.create_check_constraint(op.f("ck_booking_requests_status_valid"), "booking_requests", "status IN ('pending', 'confirmed', 'completed', 'cancelled')")
    op.create_check_constraint(op.f("ck_booking_requests_note_length"), "booking_requests", "note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 300")
    op.create_index("uq_booking_requests_one_open", "booking_requests", ["dependent_id", "provider_id"], unique=True, postgresql_where=sa.text("status IN ('pending', 'confirmed')"))
    op.create_index("uq_booking_requests_client", "booking_requests", ["requested_by", "client_id"], unique=True, postgresql_where=sa.text("client_id IS NOT NULL"))

    op.add_column("activity_log", sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("activity_log", sa.Column("subject_name", sa.String(200), server_default=sa.text("''"), nullable=False))
    op.create_foreign_key(op.f("fk_activity_log_initiated_by_users"), "activity_log", "users", ["initiated_by"], ["user_id"], ondelete="RESTRICT")
    op.create_index(op.f("ix_activity_log_initiated_by"), "activity_log", ["initiated_by"])
    op.create_check_constraint(
        op.f("ck_activity_log_type_valid"), "activity_log",
        "type IN ('org_contact', 'booking_request', 'booking_confirmed', 'booking_completed', 'booking_cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_activity_log_type_valid"), "activity_log", type_="check")
    op.drop_index(op.f("ix_activity_log_initiated_by"), table_name="activity_log")
    op.drop_constraint(op.f("fk_activity_log_initiated_by_users"), "activity_log", type_="foreignkey")
    op.drop_column("activity_log", "subject_name")
    op.drop_column("activity_log", "initiated_by")

    op.drop_index("uq_booking_requests_client", table_name="booking_requests")
    op.drop_index("uq_booking_requests_one_open", table_name="booking_requests")
    op.drop_constraint(op.f("ck_booking_requests_note_length"), "booking_requests", type_="check")
    op.drop_constraint(op.f("ck_booking_requests_status_valid"), "booking_requests", type_="check")
    op.drop_index(op.f("ix_booking_requests_requested_by"), table_name="booking_requests")
    op.drop_constraint(op.f("fk_booking_requests_requested_by_users"), "booking_requests", type_="foreignkey")
    for col in ("client_id", "updated_at", "note", "preferred_at", "requested_by"):
        op.drop_column("booking_requests", col)
