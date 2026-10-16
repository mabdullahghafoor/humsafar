"""notifications dedupe index and push tokens

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16 23:41:58.637554
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    
    op.create_table('push_tokens',
    sa.Column('token_id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token', sa.Text(), nullable=False),
    sa.Column('platform', sa.String(length=20), server_default=sa.text("'android'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('fk_push_tokens_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('token_id', name=op.f('pk_push_tokens')),
    sa.UniqueConstraint('token', name=op.f('uq_push_tokens_token'))
    )
    op.create_index(op.f('ix_push_tokens_user_id'), 'push_tokens', ['user_id'], unique=False)
    op.create_index('uq_notifications_user_dedupe', 'notifications', ['user_id', sa.text("(payload ->> 'dedupe_key')")], unique=True, postgresql_where=sa.text("(payload ->> 'dedupe_key') IS NOT NULL"))
    


def downgrade() -> None:
    
    op.drop_index('uq_notifications_user_dedupe', table_name='notifications', postgresql_where=sa.text("(payload ->> 'dedupe_key') IS NOT NULL"))
    op.drop_index(op.f('ix_push_tokens_user_id'), table_name='push_tokens')
    op.drop_table('push_tokens')
    
