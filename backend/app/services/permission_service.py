"""
Permission dashboard (Task 1.6, FR-A4) and the access gate other modules call.

Rules:
  * Only the Dependent's Primary Guardian can grant or revoke, and only for a Secondary
    Guardian linked to that Dependent (FR-A4.2). Each module is toggled independently.
  * Default deny (SDS 6.3): a Secondary has NO access to a module until a grant row with
    granted=true exists. A missing row means "no".
  * A Primary Guardian always has access to every governable module. Remote Alarm
    Override is not a module at all (it is Primary-only, FR-D3), so it can never be granted.
  * Permissions are stored per link, so they are independent per Dependent (FR-B4).
  * Revocation is immediate: `require_module_access` reads the database on every request,
    nothing is cached in the token.
  * Every change is written to audit_logs in the same transaction (FR-N3).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AuditLog,
    GuardianDependentLink,
    GuardianProfile,
    PermissionGrant,
    User,
)
from app.models.identity import PERMISSION_MODULES
from app.schemas.permissions import (
    DashboardOut,
    MyPermissionsOut,
    PermissionOut,
    SecondaryPermissions,
)
from app.services import linkage_service

ACTIVE = linkage_service.ACTIVE


def _check_module(module: str) -> None:
    if module not in PERMISSION_MODULES:
        # Includes 'remote_alarm': it is deliberately not a delegable module (FR-A4.3).
        raise AppError(
            422,
            "UNKNOWN_MODULE",
            "Unknown permission module.",
            {"allowed": list(PERMISSION_MODULES)},
        )


def _my_link(db: Session, guardian_id: uuid.UUID, dependent_id: uuid.UUID) -> GuardianDependentLink | None:
    return db.scalar(
        select(GuardianDependentLink).where(
            GuardianDependentLink.guardian_id == guardian_id,
            GuardianDependentLink.dependent_id == dependent_id,
            GuardianDependentLink.status == ACTIVE,
        )
    )


def _require_primary(db: Session, user: User, dependent_id: uuid.UUID) -> None:
    linkage_service._guardian_profile(db, user)
    if not linkage_service._is_primary_of(db, user.user_id, dependent_id):
        raise AppError(
            403, "NOT_PRIMARY_GUARDIAN", "Only this Dependent's Primary Guardian can manage permissions."
        )


def _grants_for(db: Session, link_id: uuid.UUID) -> dict[str, PermissionGrant]:
    rows = db.scalars(select(PermissionGrant).where(PermissionGrant.link_id == link_id))
    return {r.module: r for r in rows}


def _as_map(grants: dict[str, PermissionGrant]) -> dict[str, bool]:
    return {m: bool(grants[m].granted) if m in grants else False for m in PERMISSION_MODULES}


# ------------------------------------------------------------------- change

def set_permission(
    db: Session, user: User, dependent_id: uuid.UUID, module: str, guardian_id: uuid.UUID, granted: bool
) -> PermissionOut:
    _check_module(module)
    _require_primary(db, user, dependent_id)
    # Same lock the linkage code uses, so a grant cannot interleave with a link change,
    # and two simultaneous first-time grants cannot both insert a row.
    linkage_service._lock_dependent(db, dependent_id)

    link = _my_link(db, guardian_id, dependent_id)
    if link is None:
        raise AppError(404, "SECONDARY_NOT_FOUND", "That Guardian is not linked to this Dependent.")
    if link.role != "secondary":
        raise AppError(
            400, "PRIMARY_NOT_GOVERNABLE", "The Primary Guardian always has full access and cannot be restricted."
        )

    grant = db.scalar(
        select(PermissionGrant).where(PermissionGrant.link_id == link.link_id, PermissionGrant.module == module)
    )
    changed = False
    if grant is None:
        grant = PermissionGrant(link_id=link.link_id, module=module, granted=granted)
        db.add(grant)
        db.flush()  # populate grant_id and updated_at
        changed = granted  # a first-time "revoke" changes nothing: the default is already "no"
        if not granted:
            db.expire(grant)
    elif grant.granted != granted:
        grant.granted = granted
        db.flush()
        changed = True

    if changed:
        db.add(
            AuditLog(
                actor_id=user.user_id,
                action="permission_granted" if granted else "permission_revoked",
                target_type="permission_grant",
                target_id=grant.grant_id,
            )
        )
    db.commit()
    db.refresh(grant)
    return PermissionOut(
        dependent_id=dependent_id,
        guardian_id=guardian_id,
        module=module,
        granted=grant.granted,
        updated_at=grant.updated_at,
    )


# --------------------------------------------------------------------- read

def dashboard(db: Session, user: User, dependent_id: uuid.UUID) -> DashboardOut:
    """The Primary's view: every Secondary x every governable module (FR-A4.1)."""
    _require_primary(db, user, dependent_id)
    out = []
    links = [l for l in linkage_service._active_links(db, dependent_id) if l.role == "secondary"]
    for link in sorted(links, key=lambda l: l.linked_at):
        g_user = db.get(User, link.guardian_id)
        out.append(
            SecondaryPermissions(
                guardian_id=link.guardian_id,
                email=g_user.email,
                phone=g_user.phone,
                modules=_as_map(_grants_for(db, link.link_id)),
            )
        )
    return DashboardOut(dependent_id=dependent_id, modules=list(PERMISSION_MODULES), secondaries=out)


def my_permissions(db: Session, user: User, dependent_id: uuid.UUID) -> MyPermissionsOut:
    """What the calling Guardian may do for this Dependent (the app uses it to show/hide screens)."""
    linkage_service._guardian_profile(db, user)
    link = _my_link(db, user.user_id, dependent_id)
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    if link.role == "primary":
        modules = {m: True for m in PERMISSION_MODULES}
    else:
        modules = _as_map(_grants_for(db, link.link_id))
    return MyPermissionsOut(dependent_id=dependent_id, guardian_role=link.role, modules=modules)


# --------------------------------------------------------------- the gate

def check_module_access(db: Session, user: User, dependent_id: uuid.UUID, module: str) -> None:
    """
    Raise 403 unless this Guardian may use `module` for this Dependent.
    Every later feature (location, records, camera, ...) calls this before returning data.
    """
    _check_module(module)
    if user.role != "guardian":
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    link = _my_link(db, user.user_id, dependent_id)
    if link is None:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You are not linked to this Dependent.")
    # FR-A3: Guardian-side features need a verified Guardian, Secondary included. A grant
    # on its own is not enough.
    profile = db.get(GuardianProfile, user.user_id)
    if profile is None or not (profile.phone_verified or profile.cnic_verified):
        raise AppError(403, "GUARDIAN_NOT_VERIFIED", "Verify your phone number or CNIC before using this feature.")
    if link.role == "primary":
        return
    grant = db.scalar(
        select(PermissionGrant).where(PermissionGrant.link_id == link.link_id, PermissionGrant.module == module)
    )
    if grant is None or not grant.granted:
        raise AppError(
            403, "MODULE_ACCESS_DENIED", "The Primary Guardian has not granted you access to this.", {"module": module}
        )
