"""wellness_check_schedules: active, created_at; wellness_check_responses: unique prompt (Task 3.4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18 01:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wellness_check_schedules", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column(
        "wellness_check_schedules",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_wellness_prompt", "wellness_check_responses", ["wc_id", "prompted_at"])


def downgrade() -> None:
    op.drop_constraint("uq_wellness_prompt", "wellness_check_responses", type_="unique")
    op.drop_column("wellness_check_schedules", "created_at")
    op.drop_column("wellness_check_schedules", "active")
