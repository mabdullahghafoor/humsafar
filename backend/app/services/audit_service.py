"""
Reading the audit log (Task 6.6, FR-N3).

Every sensitive action is written to `audit_logs` by the feature that does it (permission changes, camera
views, record access, alarms, ...). Each row carries the Dependent it is about, so the Primary Guardian can
read the history of one Dependent. Only the Primary can read it (clarification 153); the log is append-only
and has no edit or delete endpoint.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AuditLog, User
from app.schemas.audit import AuditActor, AuditEntry, AuditList
from app.services import linkage_service, permission_service

LABELS = {
    "appointment_added": "Added an appointment",
    "appointment_changed": "Changed an appointment",
    "appointment_cancelled": "Cancelled an appointment",
    "appointment_deleted": "Deleted an appointment",
    "booking_requested": "Requested a booking",
    "booking_cancelled": "Cancelled a booking request",
    "booking_status_changed": "A booking request was updated",
    "vital_added": "Added a vital reading by hand",
    "vital_deleted": "Deleted a vital reading",
    "vitals_exported": "Exported the vitals report",
    "record_added": "Added a medical record",
    "record_downloaded": "Downloaded a medical record",
    "record_changed": "Changed a medical record",
    "record_deleted": "Deleted a medical record",
    "records_exported": "Exported the medical records",
    "record_share_created": "Created a record sharing link",
    "record_share_revoked": "Cancelled a record sharing link",
    "record_share_opened": "A record sharing link was opened",
    "record_category_hidden": "Hid a record category from a Guardian",
    "record_category_shown": "Showed a record category to a Guardian",
    "wellness_check_created": "Added a wellness check",
    "wellness_check_updated": "Changed a wellness check",
    "wellness_check_deactivated": "Turned off a wellness check",
    "wellness_check_answered": "Answered a wellness check",
    "medication_schedule_created": "Added a medication schedule",
    "medication_schedule_updated": "Changed a medication schedule",
    "medication_schedule_deactivated": "Turned off a medication schedule",
    "medication_dose_confirmed": "Marked a dose as taken",
    "medication_dose_extended": "Gave extra time for a dose",
    "medication_alert_escalated": "Sent a missed-dose alert to the Secondary Guardians",
    "camera_paired": "Paired the camera phone",
    "camera_unpaired": "Unpaired the camera phone",
    "camera_view_started": "Started watching the camera",
    "camera_view_ended": "Stopped watching the camera",
    "camera_clip_stored": "An emergency clip was saved",
    "camera_clip_viewed": "Watched an emergency clip",
    "camera_clip_deleted": "Deleted an emergency clip",
    "permission_granted": "Gave a Secondary Guardian access to a feature",
    "permission_revoked": "Took away a Secondary Guardian's access to a feature",
    "emergency_contact_set": "Set the emergency contact",
    "emergency_contact_removed": "Removed the emergency contact",
    "wearable_paired": "Paired the wearable band",
    "wearable_unpaired": "Unpaired the wearable band",
    "remote_alarm_triggered": "Sounded the remote alarm",
    "remote_alarm_stopped": "Stopped the remote alarm",
    "panic_triggered": "Panic button pressed",
    "panic_resolved": "Closed a panic alert",
}


def label_for(action: str) -> str:
    return LABELS.get(action) or action.replace("_", " ").capitalize()


def _require_primary(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    link = permission_service._my_link(db, user.user_id, dependent_id)
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    if link.role != "primary":
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can read the activity history.")
    profile = linkage_service._guardian_profile(db, user)
    if not (profile.phone_verified or profile.cnic_verified):
        raise AppError(403, "GUARDIAN_NOT_VERIFIED", "Verify your phone number or CNIC before using this feature.")


def list_entries(
    db: Session, user: User, dependent_id: uuid.UUID, *,
    action: str | None, actor_id: uuid.UUID | None, since: datetime | None, until: datetime | None,
    limit: int, offset: int,
) -> AuditList:
    _require_primary(db, user, dependent_id)
    conds = [AuditLog.dependent_id == dependent_id]
    if action:
        conds.append(AuditLog.action == action)
    if actor_id:
        conds.append(AuditLog.actor_id == actor_id)
    if since:
        conds.append(AuditLog.occurred_at >= since)
    if until:
        conds.append(AuditLog.occurred_at < until)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conds)) or 0
    rows = db.execute(
        select(AuditLog, User.full_name, User.role)
        .join(User, User.user_id == AuditLog.actor_id)
        .where(*conds)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.audit_id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        AuditEntry(
            audit_id=a.audit_id, action=a.action, label=label_for(a.action), target_type=a.target_type,
            target_id=a.target_id, occurred_at=a.occurred_at,
            actor=AuditActor(user_id=a.actor_id, full_name=name, role=role),
        )
        for a, name, role in rows
    ]
    return AuditList(items=items, total=total, limit=limit, offset=offset)
