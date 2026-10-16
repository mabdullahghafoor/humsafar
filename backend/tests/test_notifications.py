"""
Task 3.1 tests: notification service (FR-M1 priority tiers, FR-M2 acknowledgment), push tokens, recipients.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.models import (
    EscalationEvent,
    GuardianDependentLink,
    Notification,
    PushToken,
    User,
)
from app.services import device_health_service, notification_service, push_service
from tests.test_geofence import FAR, HOME, add, fix
from tests.test_linkage import assert_error, auth
from tests.test_location import send, team, utcnow
from tests.test_permissions import put

TOKEN_P = "p" * 40 + "-primary-phone-token"
TOKEN_S = "s" * 40 + "-secondary-phone-token"


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()
    p.fail = False


def me(client, token):
    return client.get("/auth/me", headers=auth(token)).json()


def inbox(client, token, **params):
    r = client.get("/notifications", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def allow_alerts(client, t, granted=True):
    assert put(client, t["pt"], t["dep"], "emergency_alerts", t["sid"], granted).status_code == 200


def breach(client, t, ago=0):
    return fix(client, t, FAR, seconds_ago=ago)


def zone_team(client):
    t = team(client)
    assert add(client, t).status_code == 201
    return t


def count(db, **where):
    db.expire_all()
    q = select(func.count()).select_from(Notification)
    for k, v in where.items():
        q = q.where(getattr(Notification, k) == v)
    return db.scalar(q)


# ------------------------------------------------------------ two tiers, who is told (FR-M1)

def test_a_breach_notifies_the_primary_at_once_as_critical(client):
    t = zone_team(client)
    assert breach(client, t).status_code == 200
    box = inbox(client, t["pt"])
    assert len(box["items"]) == 1 and box["unacknowledged_critical"] == 1
    n = box["items"][0]
    assert n["type"] == "geofence_breach" and n["priority"] == "critical"
    assert n["title"] == "Left the safe zone" and "Test User" in n["body"]
    assert n["dependent_id"] == t["dep"] and n["event_id"] and n["is_acknowledged"] is False
    assert "dedupe_key" not in n["data"] and n["data"]["tier"] == "primary"


def test_the_dependent_is_not_told_about_their_own_alert(client):
    t = zone_team(client)
    breach(client, t)
    assert inbox(client, t["dt"])["items"] == []


def test_a_secondary_hears_only_with_the_emergency_alerts_grant(client, db):
    t = zone_team(client)
    breach(client, t)
    assert inbox(client, t["st"])["items"] == []  # default deny
    allow_alerts(client, t)
    assert notification_service.dispatch_events(db) == 1  # told on the next dispatch
    got = inbox(client, t["st"])["items"]
    assert len(got) == 1 and got[0]["priority"] == "critical"
    allow_alerts(client, t, granted=False)
    breach(client, t)  # still the same open breach: nothing new for anyone
    assert len(inbox(client, t["st"])["items"]) == 1


def test_an_unverified_secondary_is_not_told_even_with_the_grant(client, db):
    from tests.test_linkage import make_secondary

    t = zone_team(client)
    ut, uid, _ = make_secondary(client, t["pt"], t["dep"], 2)  # never verified
    assert put(client, t["pt"], t["dep"], "emergency_alerts", uid, True).status_code == 200
    breach(client, t)
    assert inbox(client, ut)["items"] == []


def test_only_active_links_are_told(client, db):
    t = zone_team(client)
    allow_alerts(client, t)
    db.execute(update(GuardianDependentLink).where(GuardianDependentLink.role == "secondary").values(status="revoked"))
    db.commit()
    breach(client, t)
    assert inbox(client, t["st"])["items"] == []
    assert len(inbox(client, t["pt"])["items"]) == 1


def test_standard_all_clear_when_the_dependent_returns(client):
    t = zone_team(client)
    allow_alerts(client, t)  # the Secondary is told about the breach, so they also get the all-clear
    breach(client, t, ago=60)
    fix(client, t, HOME, seconds_ago=0)
    for tok in (t["pt"], t["st"]):
        box = inbox(client, tok)
        assert [i["priority"] for i in box["items"]] == ["standard", "critical"]  # newest first
        assert box["items"][0]["title"] == "Back in the safe zone" and box["items"][0]["data"]["resolved"] is True
        assert box["unacknowledged_critical"] == 1  # the all-clear is not critical


def test_no_all_clear_for_someone_who_was_never_told(client, db):
    t = zone_team(client)
    breach(client, t, ago=60)  # Secondary has no grant: not told
    allow_alerts(client, t)  # granted afterwards
    fix(client, t, HOME, seconds_ago=0)
    assert inbox(client, t["st"])["items"] == []
    assert len(inbox(client, t["pt"])["items"]) == 2


def test_low_battery_and_recovery(client):
    t = team(client)
    send(client, t, battery_level=12, at=utcnow() - timedelta(seconds=60))
    box = inbox(client, t["pt"])
    assert box["items"][0]["type"] == "low_battery" and box["items"][0]["priority"] == "critical"
    send(client, t, battery_level=60, at=utcnow())
    top = inbox(client, t["pt"])["items"][0]
    assert top["type"] == "low_battery" and top["priority"] == "standard" and top["title"] == "Battery recovered"


def test_connection_lost_notification(client, db):
    t = team(client)
    send(client, t, at=utcnow() - timedelta(seconds=30))
    assert device_health_service.sweep_offline(db, now=utcnow() + timedelta(hours=1)) == 1
    assert notification_service.dispatch_events(db) == 1
    n = inbox(client, t["pt"])["items"][0]
    assert n["type"] == "device_offline" and n["priority"] == "critical" and n["title"] == "Connection lost"
    assert notification_service.dispatch_events(db) == 0


def test_name_falls_back_when_the_dependent_has_no_name(client, db):
    t = zone_team(client)
    db.execute(update(User).where(User.user_id == uuid.UUID(t["dep"])).values(full_name=""))
    db.commit()
    breach(client, t)
    assert inbox(client, t["pt"])["items"][0]["body"].startswith("Your dependent")


# ------------------------------------------------------------ audiences used by Phase 3

def _event(db, dep, kind, tier="primary"):
    ev = EscalationEvent(dependent_id=uuid.UUID(dep), trigger_type=kind, tier=tier, status="open")
    db.add(ev)
    db.commit()
    return ev


def test_chain_events_follow_the_tier(client, db):
    t = team(client)
    allow_alerts(client, t)
    pid, sid = uuid.UUID(me(client, t["pt"])["user_id"]), uuid.UUID(t["sid"])
    dep = uuid.UUID(t["dep"])
    assert notification_service.recipients(db, dep, "by_tier", "primary") == [pid]
    assert notification_service.recipients(db, dep, "by_tier", "secondary") == [sid]
    assert notification_service.recipients(db, dep, "by_tier", "external_contact") == []
    allow_alerts(client, t, granted=False)
    assert notification_service.recipients(db, dep, "by_tier", "secondary") == []  # no grant, no alert


def test_a_missed_dose_goes_to_the_primary_first_then_the_secondary(client, db):
    t = team(client)
    allow_alerts(client, t)
    ev = _event(db, t["dep"], "missed_dose", "primary")
    assert notification_service.dispatch_events(db) == 1
    assert len(inbox(client, t["pt"])["items"]) == 1 and inbox(client, t["st"])["items"] == []
    ev.tier = "secondary"  # what the escalation engine (3.5) will do after the timeout
    db.commit()
    assert notification_service.dispatch_events(db) == 1
    assert len(inbox(client, t["st"])["items"]) == 1
    assert notification_service.dispatch_events(db) == 0


def test_panic_reaches_every_linked_guardian_whatever_the_permissions(client, db):
    from tests.test_linkage import make_secondary

    t = team(client)  # Secondary has NO emergency_alerts grant
    ut, uid, _ = make_secondary(client, t["pt"], t["dep"], 2)  # and an unverified one too
    _event(db, t["dep"], "panic")
    assert notification_service.dispatch_events(db) == 3
    for tok in (t["pt"], t["st"], ut):
        item = inbox(client, tok)["items"][0]
        assert item["type"] == "panic" and item["priority"] == "critical"


def test_notify_dependent_guardians_for_phase_3_features(client, db):
    t = team(client)
    out = notification_service.notify_dependent_guardians(
        db, uuid.UUID(t["dep"]), "missed_dose", "Missed medication", "Test User missed a dose.",
        audience="by_tier", tier="primary", dedupe_key="dose-1",
    )
    assert len(out) == 1
    again = notification_service.notify_dependent_guardians(
        db, uuid.UUID(t["dep"]), "missed_dose", "Missed medication", "Test User missed a dose.",
        audience="by_tier", tier="primary", dedupe_key="dose-1",
    )
    assert again == []  # same key: not sent twice


def test_notify_rejects_an_unknown_priority(client, db):
    t = team(client)
    with pytest.raises(ValueError):
        notification_service.notify(db, uuid.UUID(t["dep"]), "x", "urgent", "a", "b")


# ------------------------------------------------------------ no duplicates

def test_dispatch_twice_sends_once(client, db):
    t = zone_team(client)
    breach(client, t)
    assert notification_service.dispatch_events(db) == 0
    assert notification_service.dispatch_events(db) == 0
    assert count(db) == 1


def test_simultaneous_dispatch_sends_each_person_one_alert(client, db, engine):
    t = zone_team(client)
    allow_alerts(client, t)
    _event(db, t["dep"], "geofence_breach")  # an open event nobody has been told about yet
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return notification_service.dispatch_events(s)
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        made = sum(pool.map(run, range(6)))
    assert made == 2  # Primary + the permitted Secondary, once each
    assert count(db) == 2


def test_a_failing_dispatch_never_breaks_the_phones_upload(client, monkeypatch):
    t = zone_team(client)

    def boom(*a, **k):
        raise RuntimeError("notification bug")

    monkeypatch.setattr(notification_service, "dispatch_events", boom)
    r = breach(client, t)
    assert r.status_code == 200 and r.json()["breach_started"] is True


# ------------------------------------------------------------ acknowledgment (FR-M2)

def test_acknowledge_records_who_and_when_and_is_idempotent(client):
    t = zone_team(client)
    breach(client, t)
    n = inbox(client, t["pt"])["items"][0]
    first = client.post(f"/notifications/{n['notification_id']}/acknowledge", headers=auth(t["pt"]))
    assert first.status_code == 200 and first.json()["is_acknowledged"] is True
    stamp = first.json()["acknowledged_at"]
    again = client.post(f"/notifications/{n['notification_id']}/acknowledge", headers=auth(t["pt"]))
    assert again.status_code == 200 and again.json()["acknowledged_at"] == stamp  # first time is kept
    box = inbox(client, t["pt"])
    assert box["unacknowledged_critical"] == 0 and box["items"][0]["is_acknowledged"] is True


def test_you_cannot_acknowledge_someone_elses_notification(client):
    t = zone_team(client)
    breach(client, t)
    nid = inbox(client, t["pt"])["items"][0]["notification_id"]
    assert_error(client.post(f"/notifications/{nid}/acknowledge", headers=auth(t["st"])), 404, "NOTIFICATION_NOT_FOUND")
    assert_error(client.post(f"/notifications/{nid}/acknowledge", headers=auth(t["dt"])), 404, "NOTIFICATION_NOT_FOUND")
    assert inbox(client, t["pt"])["items"][0]["is_acknowledged"] is False


def test_acknowledge_unknown_or_anonymous(client):
    t = zone_team(client)
    assert_error(client.post(f"/notifications/{uuid.uuid4()}/acknowledge", headers=auth(t["pt"])), 404, "NOTIFICATION_NOT_FOUND")
    assert_error(client.post(f"/notifications/{uuid.uuid4()}/acknowledge"), 401, "NOT_AUTHENTICATED")
    assert_error(client.post("/notifications/not-a-uuid/acknowledge", headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.get("/notifications"), 401, "NOT_AUTHENTICATED")


def test_no_response_state_for_the_escalation_engine(client, db):
    t = zone_team(client)
    breach(client, t)
    nid = inbox(client, t["pt"])["items"][0]["notification_id"]
    assert len(notification_service.unacknowledged_critical(db)) == 1
    assert notification_service.unacknowledged_critical(db, older_than_s=300) == []  # too fresh to count
    db.execute(update(Notification).values(sent_at=utcnow() - timedelta(minutes=10)))
    db.commit()
    waiting = notification_service.unacknowledged_critical(db, older_than_s=300)
    assert len(waiting) == 1 and str(waiting[0].notification_id) == nid
    ev_id = uuid.UUID(inbox(client, t["pt"])["items"][0]["event_id"])
    assert len(notification_service.unacknowledged_critical(db, older_than_s=300, event_id=ev_id)) == 1
    assert notification_service.unacknowledged_critical(db, older_than_s=300, event_id=uuid.uuid4()) == []
    client.post(f"/notifications/{nid}/acknowledge", headers=auth(t["pt"]))
    assert notification_service.unacknowledged_critical(db, older_than_s=300) == []


# ------------------------------------------------------------ reading

def test_list_filters_paging_and_privacy(client, db):
    t = zone_team(client)
    allow_alerts(client, t)
    breach(client, t, ago=90)  # critical (Primary + Secondary? Secondary was granted before the breach)
    fix(client, t, HOME, seconds_ago=60)  # standard all-clear
    breach(client, t, ago=30)  # second breach: critical again
    box = inbox(client, t["pt"])
    assert [i["priority"] for i in box["items"]] == ["critical", "standard", "critical"]
    assert box["unacknowledged_critical"] == 2
    assert {i["priority"] for i in inbox(client, t["pt"], priority="critical")["items"]} == {"critical"}
    assert [i["priority"] for i in inbox(client, t["pt"], priority="standard")["items"]] == ["standard"]
    first = inbox(client, t["pt"], limit=2)
    assert len(first["items"]) == 2 and first["next_before"]
    rest = inbox(client, t["pt"], limit=2, before=first["next_before"])
    assert len(rest["items"]) == 1 and rest["next_before"] is None
    nid = box["items"][0]["notification_id"]
    client.post(f"/notifications/{nid}/acknowledge", headers=auth(t["pt"]))
    assert len(inbox(client, t["pt"], unacknowledged="true")["items"]) == 2
    # privacy: each person sees only their own
    mine = {i["notification_id"] for i in inbox(client, t["pt"])["items"]}
    theirs = {i["notification_id"] for i in inbox(client, t["st"])["items"]}
    assert mine.isdisjoint(theirs)


def test_list_parameter_validation(client):
    t = zone_team(client)
    for bad in ({"limit": 0}, {"limit": 101}, {"priority": "urgent"}):
        assert_error(client.get("/notifications", params=bad, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ push tokens and delivery

def test_critical_is_pushed_to_registered_phones(client, push):
    t = zone_team(client)
    r = client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json() == {"registered": True}
    breach(client, t, ago=60)
    assert len(push.sent) == 1
    m = push.sent[0]
    assert m.tokens == [TOKEN_P] and m.priority == "critical" and m.title == "Left the safe zone"
    assert m.data["type"] == "geofence_breach" and m.data["notification_id"] and m.data["event_id"]
    fix(client, t, HOME, seconds_ago=0)
    assert len(push.sent) == 2 and push.sent[1].priority == "standard"


def test_no_registered_phone_means_an_inbox_entry_but_no_push(client, push):
    t = zone_team(client)
    breach(client, t)
    assert push.sent == [] and len(inbox(client, t["pt"])["items"]) == 1


def test_a_push_failure_never_loses_the_notification(client, push):
    t = zone_team(client)
    client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["pt"]))
    push.fail = True
    breach(client, t)
    assert len(inbox(client, t["pt"])["items"]) == 1


def test_a_token_moves_to_whoever_signs_in_on_that_phone(client, db, push):
    t = zone_team(client)
    client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["pt"]))
    client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["pt"]))  # same again: still one row
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PushToken)) == 1
    client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["st"]))  # phone now used by the Secondary
    db.expire_all()
    row = db.scalar(select(PushToken))
    assert str(row.user_id) == t["sid"] and db.scalar(select(func.count()).select_from(PushToken)) == 1
    breach(client, t)
    assert push.sent == []  # the Primary no longer has a phone registered


def test_unregister_only_removes_your_own_token(client, db):
    t = zone_team(client)
    client.put("/devices/push-token", json={"token": TOKEN_P}, headers=auth(t["pt"]))
    r = client.delete("/devices/push-token", params={"token": TOKEN_P}, headers=auth(t["st"]))  # not yours
    assert r.status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PushToken)) == 1
    r = client.delete("/devices/push-token", params={"token": TOKEN_P}, headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json() == {"registered": False}
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PushToken)) == 0


def test_push_token_validation_and_login_required(client):
    t = zone_team(client)
    assert_error(client.put("/devices/push-token", json={"token": "short"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.put("/devices/push-token", json={"token": TOKEN_P, "platform": "ios"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.put("/devices/push-token", json={"token": TOKEN_P}), 401, "NOT_AUTHENTICATED")
    assert_error(client.delete("/devices/push-token", params={"token": TOKEN_P}), 401, "NOT_AUTHENTICATED")


def test_a_dependent_can_register_a_token_too(client, db):
    t = zone_team(client)
    assert client.put("/devices/push-token", json={"token": TOKEN_S}, headers=auth(t["dt"])).status_code == 200
