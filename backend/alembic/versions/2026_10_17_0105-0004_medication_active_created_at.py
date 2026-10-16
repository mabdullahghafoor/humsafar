"""medication_schedules: active and created_at (Task 3.2)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17 01:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("medication_schedules", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column(
        "medication_schedules",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_column("medication_schedules", "created_at")
    op.drop_column("medication_schedules", "active")
