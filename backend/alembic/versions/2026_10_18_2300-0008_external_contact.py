"""emergency_contacts: one per Dependent; escalation_events: external SMS state (Task 3.8)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18 23:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_emergency_contact_dependent", "emergency_contacts", ["dependent_id"])
    op.add_column("escalation_events", sa.Column("external_result", sa.String(20), nullable=True))
    op.add_column("escalation_events", sa.Column("external_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")))
    for c in ("external_attempted_at", "external_notified_at", "external_cleared_at"):
        op.add_column("escalation_events", sa.Column(c, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for c in ("external_cleared_at", "external_notified_at", "external_attempted_at", "external_attempts", "external_result"):
        op.drop_column("escalation_events", c)
    op.drop_constraint("uq_emergency_contact_dependent", "emergency_contacts", type_="unique")
