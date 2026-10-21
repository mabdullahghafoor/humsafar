"""manual vitals: diastolic, sugar context, note, retry id, doctor link can include vitals (Task 5.3)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-20 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vital_readings", sa.Column("diastolic", sa.Float(), nullable=True))
    op.add_column("vital_readings", sa.Column("context", sa.String(20), nullable=True))
    op.add_column("vital_readings", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("vital_readings", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("vital_readings", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_vital_readings_metric_valid"), "vital_readings",
        "metric_type IN ('blood_pressure', 'blood_sugar', 'spo2', 'temperature', 'heart_rate')",
    )
    op.create_check_constraint(op.f("ck_vital_readings_diastolic_for_bp"), "vital_readings", "(metric_type = 'blood_pressure') = (diastolic IS NOT NULL)")
    op.create_check_constraint(
        op.f("ck_vital_readings_context_for_sugar"), "vital_readings",
        "context IS NULL OR (metric_type = 'blood_sugar' AND context IN ('fasting', 'after_meal', 'random'))",
    )
    op.create_check_constraint(op.f("ck_vital_readings_note_length"), "vital_readings", "note IS NULL OR char_length(note) <= 200")
    op.create_index("uq_vital_readings_recorder_client", "vital_readings", ["recorded_by", "client_id"], unique=True, postgresql_where=sa.text("client_id IS NOT NULL"))
    op.add_column("record_shares", sa.Column("include_vitals", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("record_shares", "include_vitals")
    op.drop_index("uq_vital_readings_recorder_client", table_name="vital_readings")
    for c in ("note_length", "context_for_sugar", "diastolic_for_bp", "metric_valid"):
        op.drop_constraint(op.f(f"ck_vital_readings_{c}"), "vital_readings", type_="check")
    for col in ("client_id", "created_at", "note", "context", "diastolic"):
        op.drop_column("vital_readings", col)
