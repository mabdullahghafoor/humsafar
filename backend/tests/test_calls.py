"""
Task 4.4 tests: voice and video calls (FR-E2): ringing, accept / decline / end, join tokens, history, timeouts.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.models import CallLog, Notification
from app.services import call_provider, call_service, push_service
from tests.test_linkage import assert_error, auth, make_dependent
from tests.test_messaging import allow, msgteam
from tests.test_notifications import inbox

TOKEN_D = "d" * 40 + "-dependent-phone-token"


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p


@pytest.fixture(autouse=True)
def provider():
    c = call_provider.get_provider()
    c.issued.clear()
    c.fail = False
    yield c


def call(client, token, to, type="voice"):
    return client.post("/calls", json={"callee_id": to, "type": type}, headers=auth(token))


def act(client, token, cid, what):
    return client.post(f"/calls/{cid}/{what}", headers=auth(token))


def get(client, token, cid):
    r = client.get(f"/calls/{cid}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def backdate(db, cid, **cols):
    db.execute(update(CallLog).where(CallLog.call_id == uuid.UUID(cid)).values(**cols))
    db.commit()


# ------------------------------------------------------------ the normal life of a call

def test_guardian_calls_dependent_rings_accepts_and_ends(client, push, provider):
    t = msgteam(client)
    client.put("/devices/push-token", json={"token": TOKEN_D}, headers=auth(t["dt"]))
    r = call(client, t["pt"], t["dep"], "video")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["status"] == "ringing" and c["type"] == "video" and c["from_me"] is True and c["already_active"] is False
    assert c["join"]["provider"] == "mock" and c["join"]["user_id"] == t["pid"] and c["join"]["token"]  # the caller can join at once
    assert c["ring_expires_at"] is not None
    # the callee is rung with a CRITICAL notification and push, and gets NO join info before accepting
    n = inbox(client, t["dt"])["items"][0]
    assert n["type"] == "incoming_call" and n["priority"] == "critical" and n["data"]["call_id"] == c["call_id"]
    assert push.sent[-1].priority == "critical" and "calling" in push.sent[-1].title
    seen = get(client, t["dt"], c["call_id"])
    assert seen["status"] == "ringing" and seen["join"] is None and seen["from_me"] is False
    a = act(client, t["dt"], c["call_id"], "accept")
    assert a.status_code == 200 and a.json()["status"] == "accepted" and a.json()["join"]["user_id"] == t["dep"]
    assert get(client, t["pt"], c["call_id"])["status"] == "accepted"
    e = act(client, t["pt"], c["call_id"], "end")
    assert e.status_code == 200 and e.json()["status"] == "ended" and e.json()["duration_s"] >= 0 and e.json()["join"] is None


def test_dependent_can_call_a_guardian(client):
    t = msgteam(client)
    c = call(client, t["dt"], t["pid"]).json()
    assert c["status"] == "ringing" and c["type"] == "voice"
    assert inbox(client, t["pt"])["items"][0]["type"] == "incoming_call"
    assert act(client, t["pt"], c["call_id"], "accept").json()["status"] == "accepted"


def test_decline(client):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    d = act(client, t["dt"], c["call_id"], "decline")
    assert d.status_code == 200 and d.json()["status"] == "declined" and d.json()["join"] is None
    assert act(client, t["dt"], c["call_id"], "decline").json()["status"] == "declined"  # safe to repeat
    assert_error(act(client, t["dt"], c["call_id"], "accept"), 409, "CALL_NOT_RINGING")
    assert get(client, t["pt"], c["call_id"])["status"] == "declined"
    assert call(client, t["pt"], t["dep"]).status_code == 201  # free to call again


def test_caller_hangs_up_before_answer_is_cancelled_and_callee_is_told(client):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    e = act(client, t["pt"], c["call_id"], "end")
    assert e.json()["status"] == "cancelled"
    assert act(client, t["pt"], c["call_id"], "end").json()["status"] == "cancelled"  # repeat
    missed = [i for i in inbox(client, t["dt"])["items"] if i["type"] == "missed_call"]
    assert len(missed) == 1 and missed[0]["priority"] == "standard"
    assert_error(act(client, t["dt"], c["call_id"], "accept"), 409, "CALL_NOT_RINGING")


def test_callee_ending_a_ringing_call_is_a_decline(client):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    assert act(client, t["dt"], c["call_id"], "end").json()["status"] == "declined"


def test_accept_is_safe_to_repeat_and_end_twice_keeps_first_duration(client, db):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    assert act(client, t["dt"], c["call_id"], "accept").status_code == 200
    assert act(client, t["dt"], c["call_id"], "accept").json()["status"] == "accepted"
    backdate(db, c["call_id"], answered_at=datetime.now(timezone.utc) - timedelta(seconds=90))
    e1 = act(client, t["dt"], c["call_id"], "end").json()
    assert e1["status"] == "ended" and 89 <= e1["duration_s"] <= 95
    e2 = act(client, t["pt"], c["call_id"], "end").json()
    assert e2["duration_s"] == e1["duration_s"]


# ------------------------------------------------------------ who may do what

def test_only_the_callee_can_accept_or_decline(client):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    assert_error(act(client, t["pt"], c["call_id"], "accept"), 403, "FORBIDDEN")
    assert_error(act(client, t["pt"], c["call_id"], "decline"), 403, "FORBIDDEN")
    assert get(client, t["pt"], c["call_id"])["status"] == "ringing"


def test_strangers_cannot_see_or_touch_a_call(client):
    t = msgteam(client)
    allow(client, t)
    c = call(client, t["pt"], t["dep"]).json()
    for what in ("accept", "decline", "end"):
        assert_error(act(client, t["st"], c["call_id"], what), 404, "CALL_NOT_FOUND")
    assert_error(client.get(f"/calls/{c['call_id']}", headers=auth(t["st"])), 404, "CALL_NOT_FOUND")
    assert_error(client.get(f"/calls/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "CALL_NOT_FOUND")
    assert client.get("/calls", headers=auth(t["st"])).json()["items"] == []


def test_same_role_unlinked_and_self_are_refused(client):
    t = msgteam(client)
    other = make_dependent(client, 2)
    assert_error(call(client, t["pt"], t["sid"]), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(call(client, t["pt"], t["pid"]), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(call(client, t["dt"], other), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(call(client, t["pt"], str(uuid.uuid4())), 403, "NOT_LINKED_TO_DEPENDENT")


def test_needs_login_and_valid_type(client):
    t = msgteam(client)
    assert_error(client.post("/calls", json={"callee_id": t["dep"]}), 401, "NOT_AUTHENTICATED")
    assert_error(client.get("/calls"), 401, "NOT_AUTHENTICATED")
    assert_error(call(client, t["pt"], t["dep"], "hologram"), 422, "VALIDATION_ERROR")


def test_secondary_needs_communication_to_call_and_to_accept(client):
    t = msgteam(client)
    assert_error(call(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(call(client, t["dt"], t["sid"]), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    c = call(client, t["dt"], t["sid"]).json()
    allow(client, t, False)  # taken away while it rings
    assert_error(act(client, t["st"], c["call_id"], "accept"), 403, "MODULE_ACCESS_DENIED")
    assert get(client, t["dt"], c["call_id"])["status"] == "ringing"


# ------------------------------------------------------------ busy and repeats

def test_same_call_twice_returns_the_same_call(client, db):
    t = msgteam(client)
    a = call(client, t["pt"], t["dep"])
    b = call(client, t["pt"], t["dep"])
    assert (a.status_code, b.status_code) == (201, 200)
    assert b.json()["call_id"] == a.json()["call_id"] and b.json()["already_active"] is True
    assert db.scalar(select(func.count()).select_from(CallLog)) == 1
    assert len([i for i in inbox(client, t["dt"])["items"] if i["type"] == "incoming_call"]) == 1  # rung once


def test_busy_people_cannot_be_called(client):
    t = msgteam(client)
    allow(client, t)
    c = call(client, t["pt"], t["dep"]).json()
    assert_error(call(client, t["dt"], t["pid"]), 409, "USER_BUSY")  # the callee calling the caller back
    assert_error(call(client, t["st"], t["dep"]), 409, "USER_BUSY")  # a second Guardian
    act(client, t["dt"], c["call_id"], "accept")
    assert_error(call(client, t["st"], t["dep"]), 409, "USER_BUSY")
    act(client, t["pt"], c["call_id"], "end")
    assert call(client, t["st"], t["dep"]).status_code == 201  # free again


def test_both_calling_each_other_at_once_makes_one_call(client, db, monkeypatch):
    import time

    t = msgteam(client)
    gate = Barrier(2)
    real = call_service._open_calls

    def slow(*a, **k):  # widen the gap between "look for open calls" and "create one", so only the lock can keep it safe
        rows = real(*a, **k)
        time.sleep(0.4)
        return rows

    monkeypatch.setattr(call_service, "_open_calls", slow)

    def go(who):
        gate.wait()
        return call(client, t[who[0]], who[1])

    with ThreadPoolExecutor(2) as pool:
        rs = list(pool.map(go, [("pt", t["dep"]), ("dt", t["pid"])]))
    assert sorted(r.status_code for r in rs) == [201, 409]
    assert db.scalar(select(func.count()).select_from(CallLog)) == 1


def test_parallel_accept_and_decline_have_one_winner(client, db):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    gate = Barrier(2)

    def go(what):
        gate.wait()
        return act(client, t["dt"], c["call_id"], what)

    with ThreadPoolExecutor(2) as pool:
        a, d = list(pool.map(go, ["accept", "decline"]))
    assert sorted([a.status_code, d.status_code]) == [200, 409]
    final = db.scalar(select(CallLog.status).where(CallLog.call_id == uuid.UUID(c["call_id"])))
    assert final == ("accepted" if a.status_code == 200 else "declined")


# ------------------------------------------------------------ timeouts

def test_unanswered_call_becomes_missed(client, db):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    backdate(db, c["call_id"], started_at=datetime.now(timezone.utc) - timedelta(seconds=get_settings().CALL_RING_S + 5))
    seen = get(client, t["pt"], c["call_id"])
    assert seen["status"] == "missed" and seen["join"] is None
    assert_error(act(client, t["dt"], c["call_id"], "accept"), 409, "CALL_NOT_RINGING")
    missed = [i for i in inbox(client, t["dt"])["items"] if i["type"] == "missed_call"]
    assert len(missed) == 1
    assert get(client, t["pt"], c["call_id"])["status"] == "missed"
    assert len([i for i in inbox(client, t["dt"])["items"] if i["type"] == "missed_call"]) == 1  # told once


def test_a_late_call_does_not_block_the_next_one(client, db):
    t = msgteam(client)
    c = call(client, t["pt"], t["dep"]).json()
    backdate(db, c["call_id"], started_at=datetime.now(timezone.utc) - timedelta(seconds=300))
    assert call(client, t["pt"], t["dep"]).status_code == 201
    assert db.scalar(select(CallLog.status).where(CallLog.call_id == uuid.UUID(c["call_id"]))) == "missed"


def test_sweep_marks_missed_and_ends_calls_that_ran_too_long(client, db):
    t = msgteam(client)
    allow(client, t)
    c1 = call(client, t["pt"], t["dep"]).json()
    backdate(db, c1["call_id"], started_at=datetime.now(timezone.utc) - timedelta(seconds=60))
    assert call_service.sweep(db) == 1
    assert db.scalar(select(CallLog.status).where(CallLog.call_id == uuid.UUID(c1["call_id"]))) == "missed"
    assert len([i for i in inbox(client, t["dt"])["items"] if i["type"] == "missed_call"]) == 1
    assert call_service.sweep(db) == 0  # nothing left to do
    c2 = call(client, t["pt"], t["dep"]).json()
    act(client, t["dt"], c2["call_id"], "accept")
    backdate(db, c2["call_id"], answered_at=datetime.now(timezone.utc) - timedelta(seconds=get_settings().CALL_MAX_S + 10))
    assert call_service.sweep(db) == 1
    row = db.scalar(select(CallLog).where(CallLog.call_id == uuid.UUID(c2["call_id"])))
    db.refresh(row)
    assert row.status == "ended" and row.duration_s == get_settings().CALL_MAX_S


# ------------------------------------------------------------ history and provider

def test_history_pages_and_shows_both_sides(client):
    t = msgteam(client)
    ids = []
    for _ in range(4):
        c = call(client, t["pt"], t["dep"]).json()
        act(client, t["dt"], c["call_id"], "decline")
        ids.append(c["call_id"])
    seen, before = [], None
    for _ in range(4):
        params = {"limit": 3, **({"before": before} if before else {})}
        h = client.get("/calls", params=params, headers=auth(t["dt"])).json()
        seen += [i["call_id"] for i in h["items"]]
        before = h["next_before"]
        if before is None:
            break
    assert seen == ids[::-1]
    mine = client.get("/calls", headers=auth(t["pt"])).json()["items"]
    assert len(mine) == 4 and all(i["from_me"] and i["status"] == "declined" for i in mine)
    assert_error(client.get("/calls", params={"limit": 0}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_provider_failure_does_not_break_the_call(client, provider):
    t = msgteam(client)
    provider.fail = True
    c = call(client, t["pt"], t["dep"])
    assert c.status_code == 201 and c.json()["join"] is None  # the app can ask again
    provider.fail = False
    assert get(client, t["pt"], c.json()["call_id"])["join"]["token"]


def test_database_rules(db):
    from sqlalchemy.exc import IntegrityError

    from app.models import User

    a = User(email="a@x.com", phone="03001110001", password_hash="x", role="guardian", full_name="A")
    b = User(email="b@x.com", phone="03001110002", password_hash="x", role="dependent", full_name="B")
    db.add_all([a, b])
    db.commit()
    for kw in ({"caller_id": a.user_id, "callee_id": a.user_id, "type": "voice"},
               {"caller_id": a.user_id, "callee_id": b.user_id, "type": "voice", "status": "accepted"},
               {"caller_id": a.user_id, "callee_id": b.user_id, "type": "voice", "status": "teleported"}):
        db.add(CallLog(**kw))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
