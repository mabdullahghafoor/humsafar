"""escalation_events: tier_changed_at, acknowledged_at, acknowledged_by (Task 3.5)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18 02:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("escalation_events", sa.Column("tier_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("escalation_events", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("escalation_events", sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE escalation_events SET tier_changed_at = created_at")


def downgrade() -> None:
    op.drop_column("escalation_events", "acknowledged_by")
    op.drop_column("escalation_events", "acknowledged_at")
    op.drop_column("escalation_events", "tier_changed_at")
