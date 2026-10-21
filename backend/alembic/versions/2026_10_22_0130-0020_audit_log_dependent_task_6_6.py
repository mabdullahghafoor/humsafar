"""audit log knows which Dependent an action is about (Task 6.6)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-22 01:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old rows only name their target; work out the Dependent from the target's own table.
# (Rows whose target was deleted - a deleted vital, appointment, clip or contact - stay empty.)
BACKFILL = [
    ("dependent", "UPDATE audit_logs a SET dependent_id = a.target_id WHERE a.target_type IN ('dependent','camera_device') AND a.dependent_id IS NULL AND a.target_id IN (SELECT user_id FROM dependent_profiles)"),
    ("appointment", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM appointments t WHERE a.target_type = 'appointment' AND t.appointment_id = a.target_id"),
    ("vital_reading", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM vital_readings t WHERE a.target_type = 'vital_reading' AND t.reading_id = a.target_id"),
    ("medical_record", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM medical_records t WHERE a.target_type = 'medical_record' AND t.record_id = a.target_id"),
    ("record_share", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM record_shares t WHERE a.target_type = 'record_share' AND t.share_id = a.target_id"),
    ("wellness_schedule", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM wellness_check_schedules t WHERE a.target_type = 'wellness_check_schedule' AND t.wc_id = a.target_id"),
    ("wellness_response", "UPDATE audit_logs a SET dependent_id = s.dependent_id FROM wellness_check_responses t JOIN wellness_check_schedules s ON s.wc_id = t.wc_id WHERE a.target_type = 'wellness_check_response' AND t.response_id = a.target_id"),
    ("medication_schedule", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM medication_schedules t WHERE a.target_type = 'medication_schedule' AND t.schedule_id = a.target_id"),
    ("medication_confirmation", "UPDATE audit_logs a SET dependent_id = s.dependent_id FROM medication_confirmations t JOIN medication_schedules s ON s.schedule_id = t.schedule_id WHERE a.target_type = 'medication_confirmation' AND t.confirmation_id = a.target_id"),
    ("escalation_event", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM escalation_events t WHERE a.target_type = 'escalation_event' AND t.event_id = a.target_id"),
    ("booking_request", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM booking_requests t WHERE a.target_type = 'booking_request' AND t.request_id = a.target_id"),
    ("camera_session", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM camera_sessions t WHERE a.target_type = 'camera_session' AND t.session_id = a.target_id"),
    ("camera_clip", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM camera_clips t WHERE a.target_type = 'camera_clip' AND t.clip_id = a.target_id"),
    ("emergency_contact", "UPDATE audit_logs a SET dependent_id = t.dependent_id FROM emergency_contacts t WHERE a.target_type = 'emergency_contact' AND t.contact_id = a.target_id"),
    ("permission_grant", "UPDATE audit_logs a SET dependent_id = l.dependent_id FROM permission_grants t JOIN guardian_dependent_links l ON l.link_id = t.link_id WHERE a.target_type = 'permission_grant' AND t.grant_id = a.target_id"),
    ("link", "UPDATE audit_logs a SET dependent_id = l.dependent_id FROM guardian_dependent_links l WHERE a.target_type = 'guardian_dependent_link' AND l.link_id = a.target_id"),
]


def upgrade() -> None:
    op.add_column('audit_logs', sa.Column('dependent_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_audit_logs_dependent_id_dependent_profiles'), 'audit_logs', 'dependent_profiles', ['dependent_id'], ['user_id'], ondelete='SET NULL')
    op.create_index('ix_audit_logs_dependent_time', 'audit_logs', ['dependent_id', 'occurred_at'], unique=False)
    for _name, sql in BACKFILL:
        op.execute(sql)


def downgrade() -> None:
    op.drop_index('ix_audit_logs_dependent_time', table_name='audit_logs')
    op.drop_constraint(op.f('fk_audit_logs_dependent_id_dependent_profiles'), 'audit_logs', type_='foreignkey')
    op.drop_column('audit_logs', 'dependent_id')
