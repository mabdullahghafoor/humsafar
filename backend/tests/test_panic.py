"""
Task 3.6 tests: Panic Mode (FR-D2): the one deliberate exception to permission gating.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import AuditLog, EscalationEvent, LocationLog, Notification
from app.services import escalation_service as es
from app.services import notification_service, push_service
from tests.test_escalation import P
from tests.test_linkage import assert_error, auth, make_guardian
from tests.test_location import team
from tests.test_medication import other_dependent_token
from tests.test_notifications import inbox
from tests.test_permissions import put


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()


def url(t, tail=""):
    return f"/dependents/{t['dep']}/panic{tail}"


def press(client, t, token=None):
    return client.post(url(t), headers=auth(token or t["dt"]))


def panics(db):
    db.expire_all()
    return db.scalars(select(EscalationEvent).where(EscalationEvent.trigger_type == "panic").order_by(EscalationEvent.created_at)).all()


def critical(client, token):
    return [n for n in inbox(client, token)["items"] if n["priority"] == "critical"]


# ------------------------------------------------------------ the button

def test_panic_tells_every_guardian_whatever_their_permissions(client, db):
    t = team(client)
    # The Secondary has NO grants at all (the default) -- and is still told.
    r = press(client, t)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "open" and j["tier"] == "primary" and j["notified"] == 2 and j["already_active"] is False
    assert j["acknowledged_at"] is None and j["resolved_at"] is None
    for token in (t["pt"], t["st"]):
        n = critical(client, token)
        assert len(n) == 1 and (n[0]["type"], n[0]["title"]) == ("panic", "PANIC ALERT")
        assert n[0]["body"] == "Test User pressed the panic button and needs help now."
        assert n[0]["data"]["event_id"] == j["event_id"]
    assert inbox(client, t["dt"])["items"] == []  # the Dependent is not told about their own alert
    assert len(panics(db)) == 1


def test_an_explicit_revoke_does_not_stop_it_either(client):
    t = team(client)
    for module in ("emergency_alerts", "live_location", "communication"):
        assert put(client, t["pt"], t["dep"], module, t["sid"], False).status_code == 200
    assert press(client, t).json()["notified"] == 2
    assert len(critical(client, t["st"])) == 1


def test_pressing_again_changes_nothing(client, db):
    t = team(client)
    first = press(client, t).json()
    again = press(client, t)
    assert again.status_code == 200
    j = again.json()
    assert j["already_active"] is True and j["event_id"] == first["event_id"] and j["notified"] == 2
    assert len(panics(db)) == 1
    assert len(critical(client, t["pt"])) == 1 and len(critical(client, t["st"])) == 1


def test_six_taps_at_once_make_one_panic(client, db, engine):
    t = team(client)
    barrier = threading.Barrier(6)

    def tap(_):
        barrier.wait()
        return press(client, t).status_code

    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(tap, range(6)))
    assert sorted(codes) == [200] * 5 + [201]
    assert len(panics(db)) == 1
    assert len(critical(client, t["pt"])) == 1 and len(critical(client, t["st"])) == 1


def test_only_the_dependent_themself_can_press(client, db):
    t = team(client)
    assert_error(press(client, t, t["pt"]), 403, "FORBIDDEN")
    assert_error(press(client, t, t["st"]), 403, "FORBIDDEN")
    assert_error(press(client, t, other_dependent_token(client)), 403, "FORBIDDEN")
    assert client.post(url(t)).status_code == 401
    assert client.post(f"/dependents/{uuid.uuid4()}/panic", headers=auth(t["dt"])).status_code == 403
    assert panics(db) == []


def test_panic_is_in_the_audit_log(client, db):
    t = team(client)
    press(client, t)
    db.expire_all()
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "panic_triggered")).all()
    assert len(rows) == 1 and str(rows[0].actor_id) == t["dep"]



# ------------------------------------------------------------ status

def test_status_for_dependent_and_every_linked_guardian(client):
    t = team(client)
    for tok in (t["dt"], t["pt"], t["st"]):
        assert client.get(url(t), headers=auth(tok)).json() == {"active": False, "panic": None}
    press(client, t)
    for tok in (t["dt"], t["pt"], t["st"]):  # the Secondary has no grants: still sees it
        j = client.get(url(t), headers=auth(tok)).json()
        assert j["active"] is True and j["panic"]["status"] == "open" and j["panic"]["notified"] == 2


def test_status_is_private(client):
    t = team(client)
    press(client, t)
    stranger = make_guardian(client, 8)[0]
    assert_error(client.get(url(t), headers=auth(stranger)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(url(t), headers=auth(other_dependent_token(client))), 403, "FORBIDDEN")
    assert client.get(url(t)).status_code == 401


# ------------------------------------------------------------ closing

def test_dependent_cancels_and_everyone_gets_the_all_clear(client, db):
    t = team(client)
    press(client, t)
    r = client.post(url(t, "/resolve"), headers=auth(t["dt"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved" and r.json()["resolved_at"] is not None
    for token in (t["pt"], t["st"]):
        clear = [n for n in inbox(client, token)["items"] if n["priority"] == "standard"]
        assert len(clear) == 1 and clear[0]["title"] == "Panic alert closed"
        assert clear[0]["body"] == "The panic alert for Test User has been closed."
    assert client.get(url(t), headers=auth(t["pt"])).json()["active"] is False
    assert_error(client.post(url(t, "/resolve"), headers=auth(t["dt"])), 409, "NO_ACTIVE_PANIC")


def test_primary_can_close_it_a_secondary_cannot(client):
    t = team(client)
    press(client, t)
    assert_error(client.post(url(t, "/resolve"), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.post(url(t, "/resolve"), headers=auth(other_dependent_token(client))), 403, "FORBIDDEN")
    assert client.get(url(t), headers=auth(t["pt"])).json()["active"] is True
    assert client.post(url(t, "/resolve"), headers=auth(t["pt"])).json()["status"] == "resolved"
    assert client.post(url(t, "/resolve")).status_code == 401


def test_a_new_panic_can_follow_a_closed_one(client, db):
    t = team(client)
    a = press(client, t).json()
    client.post(url(t, "/resolve"), headers=auth(t["dt"]))
    r = press(client, t)
    assert r.status_code == 201 and r.json()["event_id"] != a["event_id"] and r.json()["already_active"] is False
    assert len(panics(db)) == 2
    assert len(critical(client, t["pt"])) == 2


def test_resolve_with_nothing_open(client):
    t = team(client)
    assert_error(client.post(url(t, "/resolve"), headers=auth(t["dt"])), 409, "NO_ACTIVE_PANIC")
    assert_error(client.post(url(t, "/resolve"), headers=auth(t["pt"])), 409, "NO_ACTIVE_PANIC")


# ------------------------------------------------------------ with the escalation chain (3.5)

def test_unopened_panic_goes_straight_to_the_external_contact_level(client, db):
    t = team(client)
    press(client, t)
    ev = panics(db)[0]
    assert es.sweep(db, now=ev.tier_changed_at + P - timedelta(seconds=1)) == 0
    assert es.sweep(db, now=ev.tier_changed_at + P + timedelta(seconds=1)) == 1
    assert panics(db)[0].tier == "external_contact"
    assert notification_service.dispatch_events(db) == 0  # everybody was already told: no second panic alert
    assert len(critical(client, t["pt"])) == 1 and len(critical(client, t["st"])) == 1
    assert client.get(url(t), headers=auth(t["pt"])).json()["panic"]["tier"] == "external_contact"


def test_a_guardian_opening_the_panic_stops_the_chain(client, db):
    t = team(client)
    ev_id = press(client, t).json()["event_id"]
    assert client.post(f"/escalations/{ev_id}/acknowledge", headers=auth(t["st"])).status_code == 200
    ev = panics(db)[0]
    assert es.sweep(db, now=ev.tier_changed_at + P + timedelta(seconds=1)) == 0
    assert panics(db)[0].tier == "primary"
    assert client.get(url(t), headers=auth(t["pt"])).json()["panic"]["acknowledged_at"] is not None
