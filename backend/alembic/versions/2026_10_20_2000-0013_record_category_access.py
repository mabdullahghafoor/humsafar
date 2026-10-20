"""record category restrictions per Secondary Guardian (Task 5.2)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-20 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "record_category_restrictions",
        sa.Column("restriction_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('prescription', 'lab_report', 'xray', 'other')",
            name=op.f("ck_record_category_restrictions_category_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["link_id"], ["guardian_dependent_links.link_id"],
            name=op.f("fk_record_category_restrictions_link_id_guardian_dependent_links"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("restriction_id", name=op.f("pk_record_category_restrictions")),
        sa.UniqueConstraint("link_id", "category", name=op.f("uq_restriction_link_category")),
    )
    op.create_index(op.f("ix_record_category_restrictions_link_id"), "record_category_restrictions", ["link_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_record_category_restrictions_link_id"), table_name="record_category_restrictions")
    op.drop_table("record_category_restrictions")
