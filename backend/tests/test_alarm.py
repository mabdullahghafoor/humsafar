"""
Task 3.7 tests: Remote Alarm Override (FR-D3): Primary Guardian only, not delegable.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification
from app.models.identity import PERMISSION_MODULES
from app.services import push_service
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
    return f"/dependents/{t['dep']}/alarm{tail}"


def start(client, t, token=None, **body):
    return client.post(url(t), json=body or None, headers=auth(token or t["pt"]))


def rows(db, type="remote_alarm"):
    db.expire_all()
    return db.scalars(select(Notification).where(Notification.type == type).order_by(Notification.sent_at)).all()


def alarms(client, t):
    return [n for n in inbox(client, t["dt"])["items"] if n["type"] == "remote_alarm"]


# ------------------------------------------------------------ starting

def test_primary_sounds_the_alarm(client, db, push):
    t = team(client)
    r = start(client, t)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "active" and j["duration_s"] == 60 and j["already_active"] is False
    assert j["stopped_at"] is None and j["device_acknowledged_at"] is None and j["triggered_by"] == t["pid"] if "pid" in t else True
    assert datetime.fromisoformat(j["expires_at"]) - datetime.fromisoformat(j["triggered_at"]) < timedelta(seconds=61)
    n = alarms(client, t)
    assert len(n) == 1 and n[0]["priority"] == "critical" and n[0]["data"]["alarm_id"] == j["alarm_id"]
    assert n[0]["data"]["duration_s"] == 60
    assert inbox(client, t["pt"])["items"] == [] and inbox(client, t["st"])["items"] == []  # only the Dependent's phone is told
    db.expire_all()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "remote_alarm_triggered")) is not None


def test_custom_duration_and_limits(client):
    t = team(client)
    assert start(client, t, duration_s=120).json()["duration_s"] == 120
    for bad in (5, 301, 0, -1):
        assert_error(start(client, t, duration_s=bad), 422, "VALIDATION_ERROR")
    assert_error(start(client, t, duration_s="long"), 422, "VALIDATION_ERROR")


def test_a_secondary_can_never_sound_it(client, db):
    t = team(client)
    for m in PERMISSION_MODULES:  # every permission a Secondary can be given
        assert put(client, t["pt"], t["dep"], m, t["sid"], True).status_code == 200
    assert_error(start(client, t, t["st"]), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.post(url(t, "/stop"), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.get(url(t), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert rows(db) == []


def test_nobody_else_can_start_it(client, db):
    t = team(client)
    assert_error(start(client, t, t["dt"]), 403, "FORBIDDEN")
    assert_error(start(client, t, other_dependent_token(client)), 403, "FORBIDDEN")
    stranger = make_guardian(client, 8)[0]
    assert_error(start(client, t, stranger), 403, "NOT_LINKED_TO_DEPENDENT")
    assert client.post(url(t)).status_code == 401
    assert rows(db) == []


def test_starting_again_while_it_sounds_changes_nothing(client, db):
    t = team(client)
    first = start(client, t).json()
    again = start(client, t, duration_s=200)
    assert again.status_code == 200
    j = again.json()
    assert j["already_active"] is True and j["alarm_id"] == first["alarm_id"] and j["duration_s"] == 60
    assert len(rows(db)) == 1 and len(alarms(client, t)) == 1


def test_six_requests_at_once_make_one_alarm(client, db):
    t = team(client)
    barrier = threading.Barrier(6)

    def go(_):
        barrier.wait()
        return start(client, t).status_code

    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(go, range(6)))
    assert sorted(codes) == [200] * 5 + [201]
    assert len(rows(db)) == 1


def test_a_finished_alarm_can_be_followed_by_a_new_one(client, db):
    t = team(client)
    a = start(client, t).json()
    n = rows(db)[0]
    p = dict(n.payload)
    p["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    n.payload = p
    db.commit()
    assert client.get(url(t), headers=auth(t["pt"])).json() == {"active": False, "alarm": None}
    b = start(client, t)
    assert b.status_code == 201 and b.json()["alarm_id"] != a["alarm_id"]
    assert len(rows(db)) == 2


# ------------------------------------------------------------ reading and stopping

def test_status_for_the_primary_and_the_dependents_phone(client):
    t = team(client)
    for tok in (t["pt"], t["dt"]):
        assert client.get(url(t), headers=auth(tok)).json() == {"active": False, "alarm": None}
    a = start(client, t).json()
    for tok in (t["pt"], t["dt"]):
        j = client.get(url(t), headers=auth(tok)).json()
        assert j["active"] is True and j["alarm"]["alarm_id"] == a["alarm_id"] and j["alarm"]["status"] == "active"
    assert_error(client.get(url(t), headers=auth(other_dependent_token(client))), 403, "FORBIDDEN")
    assert client.get(url(t)).status_code == 401


def test_primary_sees_when_the_phone_opened_the_alarm(client):
    t = team(client)
    start(client, t)
    nid = alarms(client, t)[0]["notification_id"]
    assert client.post(f"/notifications/{nid}/acknowledge", headers=auth(t["dt"])).status_code == 200
    assert client.get(url(t), headers=auth(t["pt"])).json()["alarm"]["device_acknowledged_at"] is not None


def test_primary_stops_the_alarm(client, db):
    t = team(client)
    a = start(client, t).json()
    r = client.post(url(t, "/stop"), headers=auth(t["pt"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "stopped" and r.json()["stopped_at"] is not None and r.json()["alarm_id"] == a["alarm_id"]
    stop = [n for n in inbox(client, t["dt"])["items"] if n["type"] == "remote_alarm_stop"]
    assert len(stop) == 1 and stop[0]["data"]["alarm_id"] == a["alarm_id"] and stop[0]["priority"] == "critical"
    assert client.get(url(t), headers=auth(t["pt"])).json()["active"] is False
    assert_error(client.post(url(t, "/stop"), headers=auth(t["pt"])), 409, "NO_ACTIVE_ALARM")
    db.expire_all()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "remote_alarm_stopped")) is not None
    assert start(client, t).status_code == 201  # a new one may follow


def test_the_dependent_can_switch_it_off_too(client):
    t = team(client)
    start(client, t)
    assert client.post(url(t, "/stop"), headers=auth(t["dt"])).json()["status"] == "stopped"
    assert_error(client.post(url(t, "/stop"), headers=auth(t["dt"])), 409, "NO_ACTIVE_ALARM")


def test_stopping_needs_the_right_person(client):
    t = team(client)
    start(client, t)
    assert_error(client.post(url(t, "/stop"), headers=auth(other_dependent_token(client))), 403, "FORBIDDEN")
    assert_error(client.post(url(t, "/stop"), headers=auth(make_guardian(client, 8)[0])), 403, "NOT_LINKED_TO_DEPENDENT")
    assert client.post(url(t, "/stop")).status_code == 401
    assert client.get(url(t), headers=auth(t["pt"])).json()["active"] is True


def test_stop_with_nothing_sounding(client):
    t = team(client)
    assert_error(client.post(url(t, "/stop"), headers=auth(t["pt"])), 409, "NO_ACTIVE_ALARM")
