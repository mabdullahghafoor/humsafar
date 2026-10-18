"""
External emergency contact fallback (Task 3.8, FR-R1).

The escalation chain (Task 3.5) moves an unanswered alert to the `external_contact` level. This job then sends ONE SMS to
the Dependent's emergency contact (sms_service; a mock until a real gateway is chosen).

Rules
- Only an OPEN alert at the external_contact level (missed dose, wellness check, panic) is texted.
- Exactly one SMS per alert: the alert row is locked (SKIP LOCKED), claimed (`external_result = 'sending'`, attempts + 1)
  and committed BEFORE the SMS is sent, so two processes can never both send it.
- Gateway down: retried every SMS_RETRY_S, up to SMS_MAX_ATTEMPTS; then the Primary Guardian is told it failed.
  (A crash between the claim and the result can, at worst, send a repeat SMS after the retry wait. Late is better than never.)
- No contact set: the Primary Guardian gets ONE critical notification. If a contact is added later, the next run texts it.
- When the alert closes after an SMS was sent, the contact gets a short "all clear" SMS (once).
- The Primary Guardian is told (standard) that the contact was messaged.
Runs every minute, after escalation_sweep and before notification_dispatch.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import EmergencyContact, EscalationEvent, GuardianDependentLink, User
from app.services import notification_service as ns
from app.services import sms_service
from app.services.escalation_service import ESCALATING

log = logging.getLogger("humsafar.external_contact")

TIER = "external_contact"
SENDING, SENT, FAILED, NO_CONTACT = "sending", "sent", "failed", "no_contact"

_WHAT = {
    "panic": "pressed the panic button and needs help",
    "missed_dose": "missed a medicine dose",
    "wellness_check": "not answered a wellness check",
}


def _primary(db: Session, dependent_id: uuid.UUID) -> User | None:
    gid = db.scalar(
        select(GuardianDependentLink.guardian_id).where(
            GuardianDependentLink.dependent_id == dependent_id,
            GuardianDependentLink.role == "primary",
            GuardianDependentLink.status == ns.ACTIVE,
        )
    )
    return db.get(User, gid) if gid else None


def alert_text(db: Session, ev: EscalationEvent, contact: EmergencyContact) -> str:
    name = ns._display_name(db, ev.dependent_id)
    primary = _primary(db, ev.dependent_id)
    call = f" Please call {primary.phone}." if primary and primary.phone else ""
    if ev.trigger_type == "panic":
        return f"HUMSAFAR URGENT: {name} pressed the panic button and needs help now.{call} Hello {contact.name}, please check on them."
    what = _WHAT.get(ev.trigger_type, "an alert")
    return f"HUMSAFAR: {name} has {what}, and their family has not answered.{call} Hello {contact.name}, please check on them."


def clear_text(db: Session, ev: EscalationEvent) -> str:
    return f"HUMSAFAR: The alert for {ns._display_name(db, ev.dependent_id)} is closed. No action is needed. Thank you."


def _tell_primary(db: Session, ev: EscalationEvent, kind: str, priority: str, title: str, body: str) -> None:
    primary = _primary(db, ev.dependent_id)
    if primary is None:
        return
    ns.notify(db, primary.user_id, "external_contact", priority, title, body, dependent_id=ev.dependent_id,
              event_id=ev.event_id, dedupe_key=f"{ev.event_id}:external:{kind}", extra={"result": kind})


# ------------------------------------------------------------------ sending the alert

def _due_ids(db: Session, now: datetime) -> list[uuid.UUID]:
    s = get_settings()
    wait = now - timedelta(seconds=s.SMS_RETRY_S)
    return list(db.scalars(
        select(EscalationEvent.event_id).where(
            EscalationEvent.status == ns.OPEN,
            EscalationEvent.trigger_type.in_(ESCALATING),
            EscalationEvent.tier == TIER,
            or_(
                EscalationEvent.external_result.is_(None),
                EscalationEvent.external_result == NO_CONTACT,  # a contact may have been added since
                (EscalationEvent.external_result.in_((FAILED, SENDING)))
                & (EscalationEvent.external_attempts < s.SMS_MAX_ATTEMPTS)
                & (EscalationEvent.external_attempted_at <= wait),
            ),
        )
    ))


def _claim(db: Session, event_id: uuid.UUID, now: datetime) -> tuple[EscalationEvent, EmergencyContact] | None:
    """Lock + re-check + mark 'sending' + commit. None if there is nothing to send (or no contact: that is recorded)."""
    s = get_settings()
    ev = db.scalar(select(EscalationEvent).where(EscalationEvent.event_id == event_id).with_for_update(skip_locked=True))
    if ev is None:
        return None
    wait = now - timedelta(seconds=s.SMS_RETRY_S)
    due = (
        ev.status == ns.OPEN and ev.tier == TIER
        and (
            ev.external_result in (None, NO_CONTACT)
            or (ev.external_result in (FAILED, SENDING) and ev.external_attempts < s.SMS_MAX_ATTEMPTS
                and ev.external_attempted_at is not None and ev.external_attempted_at <= wait)
        )
    )
    if not due:
        db.rollback()
        return None
    contact = db.scalar(select(EmergencyContact).where(EmergencyContact.dependent_id == ev.dependent_id))
    if contact is None:
        first = ev.external_result != NO_CONTACT
        ev.external_result = NO_CONTACT
        db.commit()
        if first:
            name = ns._display_name(db, ev.dependent_id)
            _tell_primary(db, ev, NO_CONTACT, ns.CRITICAL, "No emergency contact set",
                          f"The alert for {name} was not answered, and there is no emergency contact to message. Add one now.")
        return None
    ev.external_result, ev.external_attempts, ev.external_attempted_at = SENDING, ev.external_attempts + 1, now
    db.commit()
    return ev, contact


def _send_alert(db: Session, ev: EscalationEvent, contact: EmergencyContact, now: datetime) -> bool:
    ok = sms_service.send(contact.phone, alert_text(db, ev, contact))
    db.refresh(ev)
    name = ns._display_name(db, ev.dependent_id)
    if ok:
        ev.external_result, ev.external_notified_at = SENT, now
        db.commit()
        _tell_primary(db, ev, SENT, ns.STANDARD, "Emergency contact messaged",
                      f"{contact.name} was sent an SMS about the alert for {name}.")
        return True
    ev.external_result = FAILED
    db.commit()
    if ev.external_attempts >= get_settings().SMS_MAX_ATTEMPTS:
        _tell_primary(db, ev, FAILED, ns.CRITICAL, "Emergency contact could not be reached",
                      f"The SMS to {contact.name} about {name} could not be sent. Please call them yourself.")
    return False


# ------------------------------------------------------------------ the all-clear

def _clear_ids(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(
        select(EscalationEvent.event_id).where(
            EscalationEvent.status != ns.OPEN, EscalationEvent.external_result == SENT, EscalationEvent.external_cleared_at.is_(None)
        )
    ))


def _send_clear(db: Session, event_id: uuid.UUID, now: datetime) -> bool:
    ev = db.scalar(select(EscalationEvent).where(EscalationEvent.event_id == event_id).with_for_update(skip_locked=True))
    if ev is None or ev.status == ns.OPEN or ev.external_result != SENT or ev.external_cleared_at is not None:
        db.rollback()
        return False
    ev.external_cleared_at = now  # claim first: one all-clear, never two
    db.commit()
    contact = db.scalar(select(EmergencyContact).where(EmergencyContact.dependent_id == ev.dependent_id))
    if contact is None:
        return False
    sms_service.send(contact.phone, clear_text(db, ev))  # best effort: the alert itself was already delivered
    return True


# ------------------------------------------------------------------ job

def sweep(db: Session, now: datetime | None = None) -> int:
    """Send every due external-contact SMS (and all-clears). Returns how many SMS were sent."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for event_id in _due_ids(db, now):
        claimed = _claim(db, event_id, now)
        if claimed is not None and _send_alert(db, claimed[0], claimed[1], now):
            sent += 1
    for event_id in _clear_ids(db):
        if _send_clear(db, event_id, now):
            sent += 1
    return sent
