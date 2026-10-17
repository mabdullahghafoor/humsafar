"""escalation_events.reference_id and medication_confirmations.extended_until (Task 3.3)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 23:55:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("escalation_events", sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        "uq_open_event_per_reference",
        "escalation_events",
        ["reference_id", "trigger_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND reference_id IS NOT NULL"),
    )
    op.add_column("medication_confirmations", sa.Column("extended_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("medication_confirmations", "extended_until")
    op.drop_index("uq_open_event_per_reference", table_name="escalation_events")
    op.drop_column("escalation_events", "reference_id")
