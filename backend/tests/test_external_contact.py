"""
Task 3.8 tests: external emergency contact fallback (FR-R1): ONE contact per Dependent, mock SMS after the chain ran out.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.scheduler import JOBS
from app.models import AuditLog, EmergencyContact, EscalationEvent, Notification
from app.services import external_contact_service as xs
from app.services import push_service, sms_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_permissions import put

S = get_settings()
RETRY = timedelta(seconds=S.SMS_RETRY_S)
EPS = timedelta(seconds=1)
PHONE = "03001234567"
E164 = "+923001234567"


@pytest.fixture(autouse=True)
def gateways():
    p, s = push_service.get_provider(), sms_service.get_provider()
    for x in (p, s):
        x.sent.clear()
        x.fail = False
    yield s
    for x in (p, s):
        x.sent.clear()
        x.fail = False


def url(t):
    return f"/dependents/{t['dep']}/emergency-contact"


def set_contact(client, t, name="Aunt Sara", phone=PHONE, token=None):
    return client.put(url(t), json={"name": name, "phone": phone}, headers=auth(token or t["pt"]))


def alert(db, t, trigger="panic", tier="external_contact", status="open"):
    """An alert that already ran through the chain (the chain itself is tested in test_escalation)."""
    now = datetime.now(timezone.utc)
    e = EscalationEvent(dependent_id=uuid.UUID(t["dep"]), trigger_type=trigger, tier=tier, status=status, tier_changed_at=now)
    db.add(e)
    db.commit()
    return e.event_id


def row(db, event_id):
    db.expire_all()
    return db.get(EscalationEvent, event_id)


def later(db, event_id, seconds):
    return row(db, event_id).external_attempted_at + timedelta(seconds=seconds)


def titles(client, token):
    return [n["title"] for n in inbox(client, token)["items"]]


def resolve(db, event_id):
    db.execute(update(EscalationEvent).where(EscalationEvent.event_id == event_id).values(status="resolved", resolved_at=datetime.now(timezone.utc)))
    db.commit()


# ------------------------------------------------------------ the contact (API)

def test_primary_sets_reads_and_replaces_the_one_contact(client, db):
    t = team(client)
    assert_error(client.get(url(t), headers=auth(t["pt"])), 404, "EMERGENCY_CONTACT_NOT_FOUND")
    r = set_contact(client, t)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["name"] == "Aunt Sara" and first["phone"] == E164  # normalized
    r2 = set_contact(client, t, name="Uncle Bilal", phone="+92 300 7654321")
    assert r2.status_code == 200 and r2.json()["phone"] == "+923007654321"
    assert r2.json()["contact_id"] == first["contact_id"]  # replaced, not added
    assert client.get(url(t), headers=auth(t["pt"])).json()["name"] == "Uncle Bilal"
    assert db.scalar(select(func.count()).select_from(EmergencyContact)) == 1
    actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.occurred_at))]
    assert actions.count("emergency_contact_set") == 2


def test_bad_input_is_refused(client):
    t = team(client)
    for body in ({"name": "A", "phone": PHONE}, {"name": "Sara", "phone": "12345"}, {"name": "Sara"}, {"phone": PHONE}, {"name": " ", "phone": PHONE}):
        r = client.put(url(t), json=body, headers=auth(t["pt"]))
        assert_error(r, 422, "VALIDATION_ERROR")


def test_only_the_primary_can_change_it(client):
    t = team(client)
    assert_error(set_contact(client, t, token=t["st"]), 403, "NOT_PRIMARY_GUARDIAN")
    assert put(client, t["pt"], t["dep"], "emergency_alerts", t["sid"], True).status_code == 200
    assert_error(set_contact(client, t, token=t["st"]), 403, "NOT_PRIMARY_GUARDIAN")  # grants do not matter
    assert_error(client.delete(url(t), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(set_contact(client, t, token=t["dt"]), 403, "FORBIDDEN")
    assert_error(client.put(url(t), json={"name": "Sara", "phone": PHONE}), 401, "NOT_AUTHENTICATED")


def test_who_can_read_it(client):
    t = team(client)
    set_contact(client, t)
    assert_error(client.get(url(t), headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "emergency_alerts", t["sid"], True).status_code == 200
    assert client.get(url(t), headers=auth(t["st"])).json()["phone"] == E164
    assert_error(client.get(url(t), headers=auth(t["dt"])), 403, "FORBIDDEN")  # a stranger's number is not the Dependent's to read


def test_a_guardian_of_another_dependent_is_refused(client):
    t = team(client)
    from tests.test_linkage import make_guardian
    other, _, _ = make_guardian(client, 7)
    assert client.put(url(t), json={"name": "Sara", "phone": PHONE}, headers=auth(other)).status_code == 403
    assert client.get(url(t), headers=auth(other)).status_code == 403


def test_delete_and_delete_again(client, db):
    t = team(client)
    set_contact(client, t)
    assert client.delete(url(t), headers=auth(t["pt"])).status_code == 204
    assert client.delete(url(t), headers=auth(t["pt"])).status_code == 204  # safe to repeat
    assert_error(client.get(url(t), headers=auth(t["pt"])), 404, "EMERGENCY_CONTACT_NOT_FOUND")
    assert db.scalar(select(func.count()).select_from(EmergencyContact)) == 0


def test_two_quick_puts_still_leave_one_contact(client, engine, db):
    t = team(client)
    barrier = threading.Barrier(2)

    def go(i):
        barrier.wait()
        return set_contact(client, t, name=f"Person {i}", phone=f"0300123456{i}").status_code

    with ThreadPoolExecutor(2) as ex:
        codes = list(ex.map(go, (1, 2)))
    assert codes == [200, 200]
    assert db.scalar(select(func.count()).select_from(EmergencyContact)) == 1


# ------------------------------------------------------------ the SMS

def test_unanswered_panic_texts_the_contact_once(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    assert xs.sweep(db) == 1
    assert len(gateways.sent) == 1
    m = gateways.sent[0]
    assert m.to == E164
    assert "Test User" in m.body and "panic" in m.body and "Aunt Sara" in m.body and "HUMSAFAR" in m.body
    ev = row(db, e)
    assert ev.external_result == "sent" and ev.external_attempts == 1 and ev.external_notified_at is not None
    assert xs.sweep(db) == 0 and len(gateways.sent) == 1  # never twice
    note = [n for n in inbox(client, t["pt"])["items"] if n["title"] == "Emergency contact messaged"]
    assert len(note) == 1 and note[0]["priority"] == "standard"
    assert "Aunt Sara" in note[0]["body"]
    assert titles(client, t["st"]) == []  # only the Primary hears about it


@pytest.mark.parametrize("trigger,word", [("missed_dose", "medicine dose"), ("wellness_check", "wellness check")])
def test_text_for_each_kind_of_alert(client, db, gateways, trigger, word):
    t = team(client)
    set_contact(client, t)
    alert(db, t, trigger)
    assert xs.sweep(db) == 1
    assert word in gateways.sent[0].body and "family has not answered" in gateways.sent[0].body


def test_text_carries_the_primary_phone(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    alert(db, t)
    xs.sweep(db)
    assert "Please call +92" in gateways.sent[0].body


def test_nothing_is_sent_before_the_external_level(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e1 = alert(db, t, tier="primary")
    e2 = alert(db, t, "wellness_check", tier="secondary")
    assert xs.sweep(db) == 0 and gateways.sent == []
    assert row(db, e1).external_result is None and row(db, e2).external_result is None


def test_other_alert_types_are_never_texted(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    alert(db, t, "geofence_breach")
    alert(db, t, "low_battery")
    assert xs.sweep(db) == 0 and gateways.sent == []


def test_an_alert_closed_before_the_sms_is_not_texted(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    resolve(db, e)
    assert xs.sweep(db) == 0 and gateways.sent == []
    assert row(db, e).external_result is None


def test_a_guardian_who_opened_it_does_not_stop_the_sms_by_itself(client, db, gateways):
    """Opening stops the CHAIN (tier changes). An alert already at the last level is still open: the contact is texted."""
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    db.execute(update(EscalationEvent).where(EscalationEvent.event_id == e).values(acknowledged_at=datetime.now(timezone.utc)))
    db.commit()
    assert xs.sweep(db) == 1


# ------------------------------------------------------------ no contact

def test_no_contact_tells_the_primary_once(client, db, gateways):
    t = team(client)
    e = alert(db, t)
    assert xs.sweep(db) == 0 and gateways.sent == []
    assert row(db, e).external_result == "no_contact"
    n = [x for x in inbox(client, t["pt"])["items"] if x["title"] == "No emergency contact set"]
    assert len(n) == 1 and n[0]["priority"] == "critical"
    xs.sweep(db)
    xs.sweep(db)
    assert len([x for x in inbox(client, t["pt"])["items"] if x["title"] == "No emergency contact set"]) == 1


def test_a_contact_added_later_is_texted_on_the_next_run(client, db, gateways):
    t = team(client)
    e = alert(db, t)
    xs.sweep(db)
    assert gateways.sent == []
    set_contact(client, t)
    assert xs.sweep(db) == 1 and len(gateways.sent) == 1
    assert row(db, e).external_result == "sent"


def test_a_contact_removed_before_the_run_counts_as_none(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    client.delete(url(t), headers=auth(t["pt"]))
    e = alert(db, t)
    xs.sweep(db)
    assert gateways.sent == [] and row(db, e).external_result == "no_contact"


# ------------------------------------------------------------ gateway down

def test_gateway_down_is_retried_then_sent(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    gateways.fail = True
    assert xs.sweep(db) == 0
    ev = row(db, e)
    assert ev.external_result == "failed" and ev.external_attempts == 1
    assert xs.sweep(db, now=later(db, e, S.SMS_RETRY_S - 1)) == 0  # too early
    assert row(db, e).external_attempts == 1
    gateways.fail = False
    assert xs.sweep(db, now=later(db, e, S.SMS_RETRY_S + 1)) == 1
    ev = row(db, e)
    assert ev.external_result == "sent" and ev.external_attempts == 2 and len(gateways.sent) == 1
    assert "Emergency contact could not be reached" not in titles(client, t["pt"])


def test_gateway_stays_down_primary_is_told_after_the_last_try(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    gateways.fail = True
    xs.sweep(db)
    for _ in range(S.SMS_MAX_ATTEMPTS + 3):
        xs.sweep(db, now=later(db, e, S.SMS_RETRY_S + 1))
    ev = row(db, e)
    assert ev.external_result == "failed" and ev.external_attempts == S.SMS_MAX_ATTEMPTS
    n = [x for x in inbox(client, t["pt"])["items"] if x["title"] == "Emergency contact could not be reached"]
    assert len(n) == 1 and n[0]["priority"] == "critical" and "call them yourself" in n[0]["body"]


def test_a_stuck_sending_is_retried_after_the_wait(client, db, gateways):
    """The process died after the claim and before the result."""
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    now = datetime.now(timezone.utc)
    db.execute(update(EscalationEvent).where(EscalationEvent.event_id == e).values(external_result="sending", external_attempts=1, external_attempted_at=now))
    db.commit()
    assert xs.sweep(db, now=now + RETRY - EPS) == 0
    assert xs.sweep(db, now=now + RETRY + EPS) == 1
    assert row(db, e).external_result == "sent"


# ------------------------------------------------------------ all clear

def test_contact_gets_one_all_clear_when_the_alert_closes(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    xs.sweep(db)
    assert xs.sweep(db) == 0
    resolve(db, e)
    assert xs.sweep(db) == 1
    assert len(gateways.sent) == 2 and "closed" in gateways.sent[1].body and "No action" in gateways.sent[1].body
    assert row(db, e).external_cleared_at is not None
    assert xs.sweep(db) == 0 and len(gateways.sent) == 2


def test_no_all_clear_when_the_contact_was_never_texted(client, db, gateways):
    t = team(client)
    e = alert(db, t)
    xs.sweep(db)
    resolve(db, e)
    xs.sweep(db)
    assert gateways.sent == []


def test_all_clear_failure_does_not_break_the_run(client, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    xs.sweep(db)
    resolve(db, e)
    gateways.fail = True
    xs.sweep(db)  # must not raise
    assert row(db, e).external_cleared_at is not None


# ------------------------------------------------------------ races and wiring

def test_two_processes_send_one_sms(client, engine, db, gateways):
    t = team(client)
    set_contact(client, t)
    e = alert(db, t)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(4)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return xs.sweep(s)
        finally:
            s.close()

    with ThreadPoolExecutor(4) as ex:
        counts = list(ex.map(run, range(4)))
    assert sum(counts) == 1 and len(gateways.sent) == 1
    assert row(db, e).external_attempts == 1


def test_real_escalation_chain_ends_in_an_sms(client, db, gateways):
    """Panic -> nobody opens it -> the chain moves it -> the external-contact job texts."""
    from app.services import escalation_service as es
    from tests.test_escalation import P
    t = team(client)
    set_contact(client, t)
    assert client.post(f"/dependents/{t['dep']}/panic", headers=auth(t["dt"])).status_code == 201
    ev = db.scalar(select(EscalationEvent).where(EscalationEvent.trigger_type == "panic"))
    assert xs.sweep(db) == 0  # still at the Guardians' level
    es.sweep(db, now=ev.tier_changed_at + P + EPS)
    assert xs.sweep(db) == 1 and len(gateways.sent) == 1


def test_job_runs_after_the_escalation_sweep_and_before_the_dispatch():
    names = [n for n, _ in JOBS]
    assert names.index("escalation_sweep") < names.index("external_contact_sweep") < names.index("notification_dispatch")


def test_unknown_sms_provider_is_refused(monkeypatch):
    monkeypatch.setattr(sms_service, "_provider", None)
    monkeypatch.setattr(S, "SMS_PROVIDER", "nope")
    with pytest.raises(RuntimeError):
        sms_service.get_provider()
    assert sms_service.send("+923001234567", "x") is False  # send never raises
