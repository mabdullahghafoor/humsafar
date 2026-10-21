"""camera pairing and viewing sessions (Task 6.3)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21 17:45:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('camera_sessions',
    sa.Column('session_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('dependent_id', sa.UUID(), nullable=False),
    sa.Column('viewer_id', sa.UUID(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_renewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_reason', sa.String(length=30), nullable=True),
    sa.CheckConstraint("end_reason IN ('stopped', 'expired', 'unpaired', 'permission_revoked')", name=op.f('ck_camera_sessions_end_reason_valid')),
    sa.CheckConstraint('(ended_at IS NULL) = (end_reason IS NULL)', name=op.f('ck_camera_sessions_ended_together')),
    sa.CheckConstraint('expires_at > started_at', name=op.f('ck_camera_sessions_expiry_after_start')),
    sa.ForeignKeyConstraint(['dependent_id'], ['dependent_profiles.user_id'], name=op.f('fk_camera_sessions_dependent_id_dependent_profiles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['viewer_id'], ['users.user_id'], name=op.f('fk_camera_sessions_viewer_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('session_id', name=op.f('pk_camera_sessions'))
    )
    op.create_index(op.f('ix_camera_sessions_dependent_id'), 'camera_sessions', ['dependent_id'], unique=False)
    op.create_index(op.f('ix_camera_sessions_viewer_id'), 'camera_sessions', ['viewer_id'], unique=False)
    op.create_index('uq_camera_sessions_one_open', 'camera_sessions', ['dependent_id', 'viewer_id'], unique=True, postgresql_where=sa.text('ended_at IS NULL'))
    op.add_column('camera_devices', sa.Column('name', sa.String(length=60), nullable=True))
    op.add_column('camera_devices', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint('uq_camera_devices_one_per_dependent', 'camera_devices', ['dependent_id'])
    op.create_check_constraint(op.f('ck_camera_devices_stream_uri_not_blank'), 'camera_devices', 'char_length(btrim(stream_uri)) >= 1')
    op.create_check_constraint(op.f('ck_camera_devices_name_length'), 'camera_devices', 'name IS NULL OR char_length(btrim(name)) BETWEEN 1 AND 60')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_camera_devices_name_length'), 'camera_devices', type_='check')
    op.drop_constraint(op.f('ck_camera_devices_stream_uri_not_blank'), 'camera_devices', type_='check')
    op.drop_constraint('uq_camera_devices_one_per_dependent', 'camera_devices', type_='unique')
    op.drop_column('camera_devices', 'last_seen_at')
    op.drop_column('camera_devices', 'name')
    op.drop_index('uq_camera_sessions_one_open', table_name='camera_sessions', postgresql_where=sa.text('ended_at IS NULL'))
    op.drop_index(op.f('ix_camera_sessions_viewer_id'), table_name='camera_sessions')
    op.drop_index(op.f('ix_camera_sessions_dependent_id'), table_name='camera_sessions')
    op.drop_table('camera_sessions')
