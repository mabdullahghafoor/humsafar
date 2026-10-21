"""
Data retention job (Task 6.7, FR-O1).

Data is kept as long as the account is active. When an account is closed (account_service), `delete_after` is set to
now + RETENTION_DAYS (default 60). This job, run by the background scheduler, handles every account whose time has come:

* a Dependent: all data about them is DELETED (location, vitals, records and their files, clips and their files, messages and
  voice files, medication and wellness schedules, appointments, bookings, notifications, ...). The identity row is ANONYMIZED
  (name, email, phone, ID number removed) so that the audit trail still has something to point at.
* a Guardian: personal details are ANONYMIZED, links and their permissions are deleted. Messages they sent to a Dependent that is still
  active stay, shown as "Deleted user" (clarification 160).
* the audit trail (FR-N3) is the exception "required for an active audit": it is kept for AUDIT_RETENTION_DAYS after the deletion
  (default 365), then removed (clarification 161).
* `users.retention_hold = true` pauses everything above for that account (an active audit or dispute, clarification 162).

Every table must be listed in `HANDLED` below. tests/test_retention.py fails if a new table is added and not decided here.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.models import (
    ActivityLog, Appointment, AuditLog, BookingRequest, CallLog, CameraClip, CameraDevice, CameraSession, DependentProfile,
    EmergencyContact, EscalationEvent, Geofence, GuardianDependentLink, GuardianProfile, LocationLog, MedicalRecord,
    MedicationConfirmation, MedicationSchedule, Message, Notification, PermissionGrant, PushToken, RecordCategoryRestriction,
    RecordShare, User, VitalReading, WearableDevice, WellnessCheckResponse, WellnessCheckSchedule,
)
from app.services import storage_service

log = logging.getLogger(__name__)

# Tables whose rows carry a `dependent_id` and are deleted with the Dependent.
DEPENDENT_TABLES = [
    ActivityLog, Appointment, BookingRequest, CameraClip, CameraDevice, CameraSession, EmergencyContact, EscalationEvent,
    Geofence, LocationLog, MedicalRecord, RecordShare, VitalReading, WearableDevice,
]
# Every table in the database and what happens to it. Anything missing here fails the test.
HANDLED = {
    # deleted with the Dependent
    **{m.__tablename__: "dependent data: deleted" for m in DEPENDENT_TABLES},
    "medication_schedules": "dependent data: deleted (confirmations first)",
    "medication_confirmations": "dependent data: deleted",
    "wellness_check_schedules": "dependent data: deleted (responses first)",
    "wellness_check_responses": "dependent data: deleted",
    "guardian_dependent_links": "deleted (permissions and category restrictions first)",
    "permission_grants": "deleted with the link",
    "record_category_restrictions": "deleted with the link",
    "messages": "Dependent's messages deleted; a closed Guardian's stay with the sender anonymized",
    "call_logs": "Dependent's call history deleted; a closed Guardian's stay with the caller anonymized",
    "notifications": "the closed person's own, and every one that is about the Dependent, deleted",
    "push_tokens": "deleted",
    # the identity rows are anonymized, not deleted
    "users": "anonymized",
    "dependent_profiles": "anonymized",
    "guardian_profiles": "anonymized",
    # kept
    "audit_logs": "kept AUDIT_RETENTION_DAYS after the deletion, then removed",
    "healthcare_organizations": "not personal data: kept",
    "home_care_providers": "not personal data: kept",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _anonymize(user: User, now: datetime) -> None:
    tag = uuid.uuid4().hex
    user.email = f"deleted-{tag}@deleted.invalid"
    user.phone = "x" + tag[:19]
    user.full_name = "Deleted user"
    user.password_hash = security.hash_password(secrets.token_urlsafe(32))  # nobody knows it: the account can never be used again
    user.purged_at = now


def _delete_link_children(db: Session, link_ids) -> None:
    db.execute(delete(PermissionGrant).where(PermissionGrant.link_id.in_(link_ids)))
    db.execute(delete(RecordCategoryRestriction).where(RecordCategoryRestriction.link_id.in_(link_ids)))


def _purge_dependent(db: Session, user: User, now: datetime) -> list[tuple[str, str]]:
    """Delete everything about this Dependent and return the stored files to remove after the commit."""
    dep = user.user_id
    files = [("records", k) for k in db.scalars(select(MedicalRecord.file_url).where(MedicalRecord.dependent_id == dep, MedicalRecord.file_url.is_not(None)))]
    files += [("clips", k) for k in db.scalars(select(CameraClip.file_url).where(CameraClip.dependent_id == dep, CameraClip.file_url.is_not(None)))]
    files += [
        ("voice", k) for k in db.scalars(
            select(Message.content_url).where(
                or_(Message.sender_id == dep, Message.receiver_id == dep), Message.type == "priority_voice", Message.content_url.is_not(None)
            )
        )
    ]
    link_ids = select(GuardianDependentLink.link_id).where(GuardianDependentLink.dependent_id == dep)
    _delete_link_children(db, link_ids)
    sched = select(MedicationSchedule.schedule_id).where(MedicationSchedule.dependent_id == dep)
    db.execute(delete(MedicationConfirmation).where(MedicationConfirmation.schedule_id.in_(sched)))
    db.execute(delete(MedicationSchedule).where(MedicationSchedule.dependent_id == dep))
    wc = select(WellnessCheckSchedule.wc_id).where(WellnessCheckSchedule.dependent_id == dep)
    db.execute(delete(WellnessCheckResponse).where(WellnessCheckResponse.wc_id.in_(wc)))
    db.execute(delete(WellnessCheckSchedule).where(WellnessCheckSchedule.dependent_id == dep))
    for model in DEPENDENT_TABLES:
        db.execute(delete(model).where(model.dependent_id == dep))
    db.execute(delete(GuardianDependentLink).where(GuardianDependentLink.dependent_id == dep))
    db.execute(delete(Message).where(or_(Message.sender_id == dep, Message.receiver_id == dep)))
    db.execute(delete(CallLog).where(or_(CallLog.caller_id == dep, CallLog.callee_id == dep)))
    db.execute(delete(Notification).where(or_(Notification.user_id == dep, Notification.payload["dependent_id"].astext == str(dep))))
    db.execute(delete(PushToken).where(PushToken.user_id == dep))
    profile = db.get(DependentProfile, dep)
    profile.cnic, profile.dob, profile.condition_notes = None, None, None
    _anonymize(user, now)
    return files


def _purge_guardian(db: Session, user: User, now: datetime) -> list[tuple[str, str]]:
    gid = user.user_id
    link_ids = select(GuardianDependentLink.link_id).where(GuardianDependentLink.guardian_id == gid)
    _delete_link_children(db, link_ids)
    db.execute(delete(GuardianDependentLink).where(GuardianDependentLink.guardian_id == gid))
    db.execute(delete(Notification).where(Notification.user_id == gid))
    db.execute(delete(PushToken).where(PushToken.user_id == gid))
    profile = db.get(GuardianProfile, gid)
    profile.cnic_verified = profile.phone_verified = False
    _anonymize(user, now)
    return []


def purge_user(db: Session, user_id: uuid.UUID, now: datetime) -> bool:
    """Handle one due account in one transaction. False if it is no longer due (reopened, on hold or already done)."""
    user = db.scalar(select(User).where(User.user_id == user_id).with_for_update())
    if user is None or user.purged_at is not None or user.retention_hold or user.delete_after is None or user.delete_after > now:
        db.rollback()
        return False
    files = _purge_dependent(db, user, now) if user.role == "dependent" else _purge_guardian(db, user, now)
    db.commit()
    for kind, key in files:  # after the commit: a crash here leaves an unreferenced file, never a record pointing at nothing
        try:
            storage_service.get_storage(kind).delete(key)
        except OSError:
            log.exception("could not remove stored file %s/%s", kind, key)
    return True


def purge_old_audit(db: Session, now: datetime) -> int:
    cutoff = now - timedelta(days=get_settings().AUDIT_RETENTION_DAYS)
    gone = select(User.user_id).where(User.purged_at.is_not(None), User.purged_at <= cutoff, User.role == "dependent")
    n = db.execute(delete(AuditLog).where(AuditLog.dependent_id.in_(gone))).rowcount
    db.commit()
    return n


def sweep(db: Session, now: datetime | None = None) -> int:
    """Background job: delete / anonymize every closed account that is due, and drop audit rows past their keep time. Returns how many."""
    now = now or _now()
    due = db.scalars(
        select(User.user_id)
        .where(User.delete_after.is_not(None), User.delete_after <= now, User.purged_at.is_(None), User.retention_hold.is_(False))
        .order_by(User.delete_after)
        .limit(get_settings().RETENTION_BATCH)
    ).all()
    done = 0
    for uid in due:
        try:
            done += purge_user(db, uid, now)
        except Exception:  # one bad account must not stop the others
            db.rollback()
            log.exception("retention: could not purge account %s", uid)
    return done + purge_old_audit(db, now)
