"""
Task 3.5 tests: multi-level escalation chain (FR-D5): Primary -> Secondary -> external contact, by timeout.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.scheduler import JOBS
from app.models import EscalationEvent, Notification
from app.services import escalation_service as es
from app.services import notification_service, push_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_missed_dose import grant, missed_setup
from tests.test_notifications import inbox

S = get_settings()
P = timedelta(seconds=S.ESCALATION_PRIMARY_TIMEOUT_S)
SEC = timedelta(seconds=S.ESCALATION_SECONDARY_TIMEOUT_S)
EPS = timedelta(seconds=1)


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()


def ev(db, trigger="missed_dose"):
    db.expire_all()
    return db.scalar(select(EscalationEvent).where(EscalationEvent.trigger_type == trigger))


def open_alert(client, db, secondary_allowed=True):
    """A missed dose, alerted to the Primary. Returns (team, event)."""
    t, sid, due, dose = missed_setup(client, db)
    if secondary_allowed:
        grant(client, t, "emergency_alerts")
    notification_service.dispatch_events(db)
    return t, ev(db)


def alerts(client, token):
    return [n for n in inbox(client, token)["items"] if n["priority"] == "critical"]


def insert_event(db, t, trigger, tier="primary"):
    e = EscalationEvent(event_id=uuid.uuid4(), dependent_id=uuid.UUID(t["dep"]), trigger_type=trigger, tier=tier)
    db.add(e)
    db.commit()
    return e


# ------------------------------------------------------------ the chain

def test_primary_then_secondary_after_the_timeout(client, db):
    t, e = open_alert(client, db)
    assert e.tier == "primary" and e.tier_changed_at is not None
    assert len(alerts(client, t["pt"])) == 1 and alerts(client, t["st"]) == []
    assert es.sweep(db, now=e.tier_changed_at + P - EPS) == 0  # not yet
    assert ev(db).tier == "primary"
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 1
    e2 = ev(db)
    assert e2.tier == "secondary" and e2.tier_changed_at > e.tier_changed_at - EPS and e2.status == "open"
    assert notification_service.dispatch_events(db) == 1
    n = alerts(client, t["st"])
    assert len(n) == 1 and n[0]["type"] == "missed_dose" and n[0]["data"]["tier"] == "secondary"
    assert len(alerts(client, t["pt"])) == 1  # the Primary is not told again
    assert es.sweep(db, now=e2.tier_changed_at + SEC - EPS) == 0  # the Secondary has its own full timer


def test_secondary_then_external_contact(client, db):
    t, e = open_alert(client, db)
    es.sweep(db, now=e.tier_changed_at + P + EPS)
    notification_service.dispatch_events(db)
    s = ev(db)
    assert es.sweep(db, now=s.tier_changed_at + SEC - EPS) == 0
    assert es.sweep(db, now=s.tier_changed_at + SEC + EPS) == 1
    x = ev(db)
    assert x.tier == "external_contact" and x.status == "open"
    assert notification_service.dispatch_events(db) == 0  # nobody else in the app to tell
    assert es.sweep(db, now=x.tier_changed_at + timedelta(days=1)) == 0  # end of the chain


def test_a_level_with_nobody_to_tell_is_skipped(client, db):
    t, e = open_alert(client, db, secondary_allowed=False)  # the Secondary has no emergency_alerts
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 1
    assert ev(db).tier == "external_contact"
    assert alerts(client, t["st"]) == []


def test_panic_goes_from_primary_straight_to_external_contact(client, db):
    t = team(client)
    e = insert_event(db, t, "panic")
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 1
    assert ev(db, "panic").tier == "external_contact"


def test_wellness_check_follows_the_same_chain(client, db):
    from tests.test_wellness import escalated

    t, wc, due, r = escalated(client, db)
    grant(client, t, "emergency_alerts")
    notification_service.dispatch_events(db)
    e = ev(db, "wellness_check")
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 1
    notification_service.dispatch_events(db)
    n = alerts(client, t["st"])
    assert len(n) == 1 and n[0]["type"] == "wellness_check" and n[0]["data"]["tier"] == "secondary"


def test_events_that_are_told_once_do_not_escalate(client, db):
    t = team(client)
    e = insert_event(db, t, "geofence_breach")
    assert es.sweep(db, now=e.tier_changed_at + timedelta(days=1)) == 0
    assert ev(db, "geofence_breach").tier == "primary"


def test_a_closed_event_does_not_escalate(client, db):
    t, e = open_alert(client, db)
    db.execute(update(EscalationEvent).values(status="resolved", resolved_at=datetime.now(timezone.utc)))
    db.commit()
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 0
    assert ev(db).tier == "primary"


# ------------------------------------------------------------ acknowledgment stops the chain

def test_primary_opening_the_alert_stops_the_chain(client, db):
    t, e = open_alert(client, db)
    n = alerts(client, t["pt"])[0]
    assert client.post(f"/notifications/{n['notification_id']}/acknowledge", headers=auth(t["pt"])).status_code == 200
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 0
    x = ev(db)
    assert x.tier == "primary" and x.acknowledged_at is not None and x.acknowledged_by is not None
    assert es.sweep(db, now=e.tier_changed_at + timedelta(days=1)) == 0


def test_acknowledge_endpoint(client, db):
    t, e = open_alert(client, db)
    u = f"/escalations/{e.event_id}/acknowledge"
    a = client.post(u, headers=auth(t["pt"]))
    assert a.status_code == 200, a.text
    j = a.json()
    assert j["acknowledged_at"] is not None and j["tier"] == "primary" and j["next_escalation_at"] is None
    assert client.post(u, headers=auth(t["pt"])).json()["acknowledged_at"] == j["acknowledged_at"]  # first time kept
    assert alerts(client, t["pt"])[0]["acknowledged_at"] is not None  # the notification itself is acknowledged
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 0


def test_acknowledge_only_by_someone_who_was_told(client, db):
    t, e = open_alert(client, db)
    u = f"/escalations/{e.event_id}/acknowledge"
    assert_error(client.post(u, headers=auth(t["st"])), 404, "ESCALATION_NOT_FOUND")  # not told yet
    assert_error(client.post(u, headers=auth(t["dt"])), 404, "ESCALATION_NOT_FOUND")
    assert_error(client.post(f"/escalations/{uuid.uuid4()}/acknowledge", headers=auth(t["pt"])), 404, "ESCALATION_NOT_FOUND")
    assert client.post(u).status_code == 401
    assert ev(db).acknowledged_at is None


def test_secondary_opening_the_alert_stops_it_before_the_external_contact(client, db):
    t, e = open_alert(client, db)
    es.sweep(db, now=e.tier_changed_at + P + EPS)
    notification_service.dispatch_events(db)
    s = ev(db)
    assert client.post(f"/escalations/{s.event_id}/acknowledge", headers=auth(t["st"])).status_code == 200
    assert es.sweep(db, now=s.tier_changed_at + SEC + EPS) == 0
    assert ev(db).tier == "secondary"


def test_opening_the_all_clear_does_not_count(client, db):
    t, e = open_alert(client, db)
    first = db.scalar(select(Notification).where(Notification.payload["event_id"].astext == str(e.event_id)))
    db.add(Notification(notification_id=uuid.uuid4(), user_id=first.user_id, type="missed_dose", priority="standard",
                        payload={"event_id": str(e.event_id), "dedupe_key": f"{e.event_id}:resolved"},
                        acknowledged_at=datetime.now(timezone.utc)))
    db.commit()
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 1


def test_late_acknowledgment_found_by_the_sweep_wins(client, db):
    t, e = open_alert(client, db)
    n = alerts(client, t["pt"])[0]
    client.post(f"/notifications/{n['notification_id']}/acknowledge", headers=auth(t["pt"]))
    assert ev(db).acknowledged_at is None  # tapped the notification, event not yet marked
    assert es.sweep(db, now=e.tier_changed_at + P + EPS) == 0
    assert ev(db).acknowledged_at is not None


# ------------------------------------------------------------ manual escalation, list, races

def test_guardian_escalating_by_hand_restarts_the_timer(client, db):
    t, sid, due, dose = missed_setup(client, db)
    grant(client, t, "emergency_alerts")
    grant(client, t, "medication_management")
    notification_service.dispatch_events(db)
    before = ev(db).tier_changed_at
    r = client.post(f"/dependents/{t['dep']}/medication-doses/{dose.confirmation_id}/escalate", headers=auth(t["pt"]))
    assert r.status_code == 200, r.text
    after = ev(db)
    assert after.tier == "secondary" and after.tier_changed_at > before
    assert es.sweep(db, now=after.tier_changed_at + SEC - EPS) == 0
    assert es.sweep(db, now=after.tier_changed_at + SEC + EPS) == 1
    assert ev(db).tier == "external_contact"


def test_list_the_chain(client, db):
    t, e = open_alert(client, db, secondary_allowed=False)
    u = f"/dependents/{t['dep']}/escalations"
    j = client.get(u, headers=auth(t["pt"])).json()
    assert (j["primary_timeout_s"], j["secondary_timeout_s"]) == (S.ESCALATION_PRIMARY_TIMEOUT_S, S.ESCALATION_SECONDARY_TIMEOUT_S)
    assert len(j["items"]) == 1
    i = j["items"][0]
    assert i["event_id"] == str(e.event_id) and i["trigger_type"] == "missed_dose" and i["tier"] == "primary"
    assert datetime.fromisoformat(i["next_escalation_at"]) == e.tier_changed_at + P
    assert client.get(u, params={"status": "resolved"}, headers=auth(t["pt"])).json()["items"] == []
    assert_error(client.get(u, params={"status": "bogus"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert client.get(u, headers=auth(t["st"])).status_code == 403  # no emergency_alerts yet
    grant(client, t, "emergency_alerts")
    assert client.get(u, headers=auth(t["st"])).status_code == 200
    assert_error(client.get(u, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert client.get(u).status_code == 401


def test_list_shows_the_end_of_the_chain(client, db):
    t, e = open_alert(client, db, secondary_allowed=False)
    es.sweep(db, now=e.tier_changed_at + P + EPS)
    i = client.get(f"/dependents/{t['dep']}/escalations", headers=auth(t["pt"])).json()["items"][0]
    assert i["tier"] == "external_contact" and i["next_escalation_at"] is None


def test_two_processes_move_it_once(client, db, engine):
    t, e = open_alert(client, db)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)
    now = e.tier_changed_at + P + EPS

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return es.sweep(s, now=now)
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(run, range(6))) == 1
    assert ev(db).tier == "secondary"  # moved one level, not two


def test_job_is_registered_before_the_dispatch():
    names = [n for n, _ in JOBS]
    assert names.index("escalation_sweep") < names.index("notification_dispatch")
    assert names.index("medication_missed_sweep") < names.index("escalation_sweep")
    assert names.index("wellness_sweep") < names.index("escalation_sweep")
