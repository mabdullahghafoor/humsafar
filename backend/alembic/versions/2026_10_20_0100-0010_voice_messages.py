"""messages: voice message length and rules (Task 4.3)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20 01:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("duration_s", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_messages_voice_has_audio"), "messages", "type <> 'priority_voice' OR (content_url IS NOT NULL AND duration_s IS NOT NULL)"
    )
    op.create_check_constraint(op.f("ck_messages_duration_range"), "messages", "duration_s IS NULL OR duration_s BETWEEN 1 AND 600")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_messages_duration_range"), "messages", type_="check")
    op.drop_constraint(op.f("ck_messages_voice_has_audio"), "messages", type_="check")
    op.drop_column("messages", "duration_s")
