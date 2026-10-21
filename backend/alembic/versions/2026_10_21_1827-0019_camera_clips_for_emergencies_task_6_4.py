"""camera clips for emergencies (Task 6.4)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-21 18:27:30.994002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('camera_clips', sa.Column('event_id', sa.UUID(), nullable=True))
    op.add_column('camera_clips', sa.Column('status', sa.String(length=15), server_default='requested', nullable=False))
    op.add_column('camera_clips', sa.Column('duration_s', sa.Integer(), nullable=True))
    op.add_column('camera_clips', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('camera_clips', sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('camera_clips', sa.Column('size_bytes', sa.BigInteger(), nullable=True))
    op.add_column('camera_clips', sa.Column('content_type', sa.String(length=30), nullable=True))
    op.alter_column('camera_clips', 'file_url',
               existing_type=sa.TEXT(),
               nullable=True)
    op.execute("UPDATE camera_clips SET status = 'stored', uploaded_at = captured_at WHERE file_url IS NOT NULL")  # clips from before this task (none are written by earlier tasks)
    op.create_check_constraint(op.f('ck_camera_clips_trigger_type_valid'), 'camera_clips', "trigger_type IN ('panic', 'remote_alarm')")
    op.create_check_constraint(op.f('ck_camera_clips_status_valid'), 'camera_clips', "status IN ('requested', 'stored', 'missed')")
    op.create_check_constraint(op.f('ck_camera_clips_file_when_stored'), 'camera_clips', "(status = 'stored') = (file_url IS NOT NULL)")
    op.create_check_constraint(op.f('ck_camera_clips_size_positive'), 'camera_clips', 'size_bytes IS NULL OR size_bytes > 0')
    op.create_index('uq_camera_clips_one_per_event', 'camera_clips', ['dependent_id', 'trigger_type', 'event_id'], unique=True, postgresql_where=sa.text('event_id IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_camera_clips_one_per_event', table_name='camera_clips', postgresql_where=sa.text('event_id IS NOT NULL'))
    for c in ('size_positive', 'file_when_stored', 'status_valid', 'trigger_type_valid'):
        op.drop_constraint(op.f('ck_camera_clips_' + c), 'camera_clips', type_='check')
    op.execute('DELETE FROM camera_clips WHERE file_url IS NULL')  # requests that never got a file
    op.alter_column('camera_clips', 'file_url',
               existing_type=sa.TEXT(),
               nullable=False)
    op.drop_column('camera_clips', 'content_type')
    op.drop_column('camera_clips', 'size_bytes')
    op.drop_column('camera_clips', 'uploaded_at')
    op.drop_column('camera_clips', 'expires_at')
    op.drop_column('camera_clips', 'duration_s')
    op.drop_column('camera_clips', 'status')
    op.drop_column('camera_clips', 'event_id')
