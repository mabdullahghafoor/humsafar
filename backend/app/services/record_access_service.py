"""
Field-level access control on medical records (Task 5.2, FR-G2).

The Primary Guardian can hide single record categories from a Secondary Guardian, separately for each
Dependent. Two gates, both must pass for a Secondary:
  1. the `health_records` module is granted (Task 1.6, FR-A4), then
  2. the category is not hidden (this file).
The Primary and the Dependent always see every category. Nothing is cached: removing or adding a restriction
takes effect on the next request. Every change is written to the audit log (FR-N3).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AuditLog, RecordCategoryRestriction, User
from app.models.medical import RECORD_CATEGORIES
from app.schemas.records import MyRecordAccess, RecordAccessDashboard, RecordAccessOut, SecondaryRecordAccess
from app.services import linkage_service, permission_service


def hidden_categories(db: Session, link_id: uuid.UUID) -> set[str]:
    return set(db.scalars(select(RecordCategoryRestriction.category).where(RecordCategoryRestriction.link_id == link_id)))


def visible_for(db: Session, user: User, dependent_id: uuid.UUID) -> tuple[str, ...]:
    """The categories this person may see. Does not check the module gate (the caller does that first)."""
    if user.role == "dependent":
        return RECORD_CATEGORIES if user.user_id == dependent_id else ()
    link = permission_service._my_link(db, user.user_id, dependent_id)
    if link is None:
        return ()
    if link.role == "primary":
        return RECORD_CATEGORIES
    hidden = hidden_categories(db, link.link_id)
    return tuple(c for c in RECORD_CATEGORIES if c not in hidden)


def set_access(
    db: Session, user: User, dependent_id: uuid.UUID, category: str, guardian_id: uuid.UUID, visible: bool
) -> RecordAccessOut:
    """Primary only: show or hide one category for one Secondary Guardian."""
    if category not in RECORD_CATEGORIES:
        raise AppError(422, "UNKNOWN_CATEGORY", "Unknown record category.", {"allowed": list(RECORD_CATEGORIES)})
    permission_service._require_primary(db, user, dependent_id)
    linkage_service._lock_dependent(db, dependent_id)  # same lock as permission changes: two changes cannot interleave

    link = permission_service._my_link(db, guardian_id, dependent_id)
    if link is None:
        raise AppError(404, "SECONDARY_NOT_FOUND", "That Guardian is not linked to this Dependent.")
    if link.role != "secondary":
        raise AppError(400, "PRIMARY_NOT_GOVERNABLE", "The Primary Guardian always has full access and cannot be restricted.")

    row = db.scalar(
        select(RecordCategoryRestriction).where(
            RecordCategoryRestriction.link_id == link.link_id, RecordCategoryRestriction.category == category
        )
    )
    changed = False
    if visible and row is not None:
        db.execute(delete(RecordCategoryRestriction).where(RecordCategoryRestriction.restriction_id == row.restriction_id))
        changed = True
    elif not visible and row is None:
        db.add(RecordCategoryRestriction(link_id=link.link_id, category=category))
        changed = True
    if changed:
        db.add(AuditLog(
            actor_id=user.user_id, action="record_category_shown" if visible else "record_category_hidden",
            target_type="guardian_dependent_link", target_id=link.link_id, dependent_id=dependent_id,
        ))
    db.commit()
    hidden = hidden_categories(db, link.link_id)
    return RecordAccessOut(
        dependent_id=dependent_id, guardian_id=guardian_id, category=category, visible=category not in hidden,
        visible_categories=[c for c in RECORD_CATEGORIES if c not in hidden],
    )


def dashboard(db: Session, user: User, dependent_id: uuid.UUID) -> RecordAccessDashboard:
    """The Primary's view: every Secondary, whether `health_records` is granted, and which categories they see."""
    permission_service._require_primary(db, user, dependent_id)
    out = []
    links = [l for l in linkage_service._active_links(db, dependent_id) if l.role == "secondary"]
    for link in sorted(links, key=lambda l: l.linked_at):
        g = db.get(User, link.guardian_id)
        hidden = hidden_categories(db, link.link_id)
        grants = permission_service._grants_for(db, link.link_id)
        out.append(SecondaryRecordAccess(
            guardian_id=link.guardian_id, email=g.email, phone=g.phone,
            health_records_granted=bool(grants["health_records"].granted) if "health_records" in grants else False,
            categories={c: c not in hidden for c in RECORD_CATEGORIES},
        ))
    return RecordAccessDashboard(dependent_id=dependent_id, categories=list(RECORD_CATEGORIES), secondaries=out)


def my_access(db: Session, user: User, dependent_id: uuid.UUID) -> MyRecordAccess:
    """What the caller may see (the app uses it to show or hide category tabs). Same module gate as the vault."""
    from app.services import records_service  # local import: records_service imports this file

    records_service.authorize(db, user, dependent_id)
    vis = visible_for(db, user, dependent_id)
    return MyRecordAccess(
        dependent_id=dependent_id, categories={c: c in vis for c in RECORD_CATEGORIES}, visible_categories=list(vis)
    )
