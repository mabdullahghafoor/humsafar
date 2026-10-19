"""call_logs: status, provider room, answered / ended time (Task 4.4)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20 02:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_logs", sa.Column("status", sa.String(15), nullable=False, server_default=sa.text("'ringing'")))
    op.add_column("call_logs", sa.Column("room_id", sa.String(64), nullable=True))
    op.add_column("call_logs", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("call_logs", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f("ck_call_logs_status_valid"), "call_logs", "status IN ('ringing', 'accepted', 'ended', 'declined', 'missed', 'cancelled')")
    op.create_check_constraint(op.f("ck_call_logs_answered_when_accepted"), "call_logs", "status NOT IN ('accepted', 'ended') OR answered_at IS NOT NULL")
    op.create_check_constraint(op.f("ck_call_logs_not_self"), "call_logs", "caller_id <> callee_id")
    op.create_index("ix_call_logs_open", "call_logs", ["status", "started_at"], postgresql_where=sa.text("status IN ('ringing', 'accepted')"))


def downgrade() -> None:
    op.drop_index("ix_call_logs_open", table_name="call_logs")
    for c in ("not_self", "answered_when_accepted", "status_valid"):
        op.drop_constraint(op.f(f"ck_call_logs_{c}"), "call_logs", type_="check")
    for c in ("ended_at", "answered_at", "room_id", "status"):
        op.drop_column("call_logs", c)
