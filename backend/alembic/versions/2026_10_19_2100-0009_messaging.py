"""messages: text body, read time, client id for safe retries (Task 4.2)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19 21:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_check_constraint(op.f("ck_messages_text_has_body"), "messages", "type <> 'text' OR body IS NOT NULL")
    op.create_check_constraint(op.f("ck_messages_body_length"), "messages", "body IS NULL OR char_length(body) BETWEEN 1 AND 2000")
    op.create_index("uq_messages_sender_client", "messages", ["sender_id", "client_id"], unique=True, postgresql_where=sa.text("client_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_messages_sender_client", table_name="messages")
    op.drop_constraint(op.f("ck_messages_body_length"), "messages", type_="check")
    op.drop_constraint(op.f("ck_messages_text_has_body"), "messages", type_="check")
    for c in ("client_id", "read_at", "body"):
        op.drop_column("messages", c)
