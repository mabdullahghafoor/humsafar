"""
External emergency contact (Task 3.8, FR-R1): the ONE person outside the app who is messaged when the escalation chain
(Primary, then Secondary Guardians) has not been answered.
  PUT    /dependents/{id}/emergency-contact   set or replace it (PRIMARY Guardian only)
  GET    /dependents/{id}/emergency-contact   read it (the Primary, or a Secondary with `emergency_alerts`)
  DELETE /dependents/{id}/emergency-contact   remove it (PRIMARY Guardian only; safe to repeat)
The phone number of a person who is not a user is personal data: the Dependent cannot read it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AuditLog, EmergencyContact, User
from app.schemas.emergency_contact import ContactIn, ContactOut
from app.services import linkage_service, permission_service

MODULE = "emergency_alerts"


def _require_primary(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    link = permission_service._my_link(db, user.user_id, dependent_id)
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    if link.role != "primary":
        raise AppError(403, "NOT_PRIMARY_GUARDIAN", "Only the Primary Guardian can set the emergency contact.")
    profile = linkage_service._guardian_profile(db, user)
    if not (profile.phone_verified or profile.cnic_verified):
        raise AppError(403, "GUARDIAN_NOT_VERIFIED", "Verify your phone number or CNIC before using this feature.")


def _out(c: EmergencyContact) -> ContactOut:
    return ContactOut(contact_id=c.contact_id, name=c.name, phone=c.phone)


def get_for(db: Session, dependent_id: uuid.UUID) -> EmergencyContact | None:
    return db.scalar(select(EmergencyContact).where(EmergencyContact.dependent_id == dependent_id))


def put(db: Session, user: User, dependent_id: uuid.UUID, body: ContactIn) -> ContactOut:
    _require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    stmt = (
        pg_insert(EmergencyContact)
        .values(contact_id=uuid.uuid4(), dependent_id=dependent_id, name=body.name, phone=body.phone)
        .on_conflict_do_update(constraint="uq_emergency_contact_dependent", set_={"name": body.name, "phone": body.phone})
        .returning(EmergencyContact.contact_id)
    )
    cid = db.execute(stmt).scalar()
    db.add(AuditLog(actor_id=user.user_id, action="emergency_contact_set", target_type="emergency_contact", target_id=cid, dependent_id=dependent_id))
    db.commit()
    return _out(db.get(EmergencyContact, cid))


def read(db: Session, user: User, dependent_id: uuid.UUID) -> ContactOut:
    permission_service.check_module_access(db, user, dependent_id, MODULE)  # Dependents are refused (FORBIDDEN)
    c = get_for(db, dependent_id)
    if c is None:
        raise AppError(404, "EMERGENCY_CONTACT_NOT_FOUND", "No emergency contact has been set.")
    return _out(c)


def delete(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    _require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)
    c = get_for(db, dependent_id)
    if c is not None:
        db.add(AuditLog(actor_id=user.user_id, action="emergency_contact_removed", target_type="emergency_contact", target_id=c.contact_id, dependent_id=dependent_id))
        db.delete(c)
    db.commit()
