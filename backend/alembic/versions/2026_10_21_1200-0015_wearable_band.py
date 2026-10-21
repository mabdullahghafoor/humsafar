"""wearable band: one band per Dependent, address format, sample uniqueness, source/metric rule (Task 5.4)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-21 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wearable_devices", sa.Column("name", sa.String(60), nullable=True))
    op.create_unique_constraint("uq_wearable_one_per_dependent", "wearable_devices", ["dependent_id"])
    op.create_check_constraint(op.f("ck_wearable_devices_address_format"), "wearable_devices", "ble_address ~ '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'")
    op.create_check_constraint(op.f("ck_wearable_devices_name_length"), "wearable_devices", "name IS NULL OR char_length(btrim(name)) BETWEEN 1 AND 60")
    op.create_check_constraint(
        op.f("ck_vital_readings_source_metric_valid"), "vital_readings",
        "(source = 'manual' AND metric_type IN ('blood_pressure', 'blood_sugar', 'spo2', 'temperature')) "
        "OR (source = 'wearable' AND metric_type IN ('heart_rate', 'spo2', 'temperature'))",
    )
    op.create_index(
        "uq_vital_readings_wearable_sample", "vital_readings", ["dependent_id", "metric_type", "recorded_at"],
        unique=True, postgresql_where=sa.text("source = 'wearable'"),
    )


def downgrade() -> None:
    op.drop_index("uq_vital_readings_wearable_sample", table_name="vital_readings")
    op.drop_constraint(op.f("ck_vital_readings_source_metric_valid"), "vital_readings", type_="check")
    op.drop_constraint(op.f("ck_wearable_devices_name_length"), "wearable_devices", type_="check")
    op.drop_constraint(op.f("ck_wearable_devices_address_format"), "wearable_devices", type_="check")
    op.drop_constraint("uq_wearable_one_per_dependent", "wearable_devices", type_="unique")
    op.drop_column("wearable_devices", "name")
