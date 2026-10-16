"""add users.full_name

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16 22:06:00.971213
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default '' lets existing rows (test data) stay valid; the API requires a real name.
    op.add_column("users", sa.Column("full_name", sa.String(length=100), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "full_name")
