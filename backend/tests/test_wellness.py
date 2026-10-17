"""
Task 3.4 tests: Guardian wellness check (FR-D4): schedule, prompt, answer, grace period, activity cross-check.
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
from app.models import AuditLog, EscalationEvent, LocationLog, Notification, WellnessCheckResponse, WellnessCheckSchedule
from app.services import notification_service, push_service
from app.services import wellness_service as ws
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_medication import local_hhmm, other_dependent_token
from tests.test_notifications import inbox
from tests.test_permissions import put

GRACE = timedelta(minutes=30)


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()


def url(t, tail=""):
    return f"/dependents/{t['dep']}/wellness-checks{tail}"


def add(client, token, t, times=("08:00",), **over):
    return client.post(url(t), json={"times": list(times), **over}, headers=auth(token))


def mk(client, t, minutes_ahead=20, **over):
    """One check due `minutes_ahead` minutes from now. Returns (wc_id, due_utc)."""
    hhmm, due = local_hhmm(minutes_ahead)
    r = add(client, t["pt"], t, times=[hhmm], **over)
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["wc_id"], due


def responses(db):
    db.expire_all()
    return db.scalars(select(WellnessCheckResponse).order_by(WellnessCheckResponse.prompted_at)).all()


def events(db, **where):
    db.expire_all()
    q = select(EscalationEvent).where(EscalationEvent.trigger_type == "wellness_check")
    for k, v in where.items():
        q = q.where(getattr(EscalationEvent, k) == v)
    return db.scalars(q).all()


def prompted(client, db, t, minutes_ahead=20, **over):
    wc, due = mk(client, t, minutes_ahead, **over)
    assert ws.tick(db, now=due) == 1
    return wc, due, responses(db)[0]


def respond(client, token, rid):
    return client.post(f"/wellness-checks/{rid}/respond", headers=auth(token))


def fix_at(db, dep_id, when):
    db.add(LocationLog(dependent_id=uuid.UUID(str(dep_id)), lat=24.86, lng=67.0, recorded_at=when))
    db.commit()


def grant(client, t, module="emergency_alerts", granted=True):
    assert put(client, t["pt"], t["dep"], module, t["sid"], granted).status_code == 200


def escalated(client, db):
    """A check that was prompted, left unanswered with no device activity, and escalated."""
    t = team(client)
    wc, due, r = prompted(client, db, t)
    assert ws.sweep(db, now=due + GRACE + timedelta(minutes=1)) == 1
    return t, wc, due, r


# ------------------------------------------------------------ schedule

def test_create_checks_sorted_with_default_grace(client):
    t = team(client)
    r = add(client, t["pt"], t, times=["20:00", "08:00", "08:00"])
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["timezone"] == "Asia/Karachi" and j["default_times"] == ["08:00", "14:00", "20:00"]
    assert [i["time"] for i in j["items"]] == ["08:00", "20:00"]
    assert j["items"][0]["grace_period_min"] == 30 and j["items"][0]["active"] is True


@pytest.mark.parametrize(
    "over",
    [
        {"times": []},
        {"times": ["08:00", "12:00", "16:00", "20:00"]},
        {"times": ["8am"]},
        {"times": ["25:00"]},
        {"grace_period_min": 4},
        {"grace_period_min": 181},
        {"grace_period_min": 0},
    ],
)
def test_bad_checks_are_rejected(client, over):
    t = team(client)
    body = {"times": ["08:00"], **over}
    assert_error(client.post(url(t), json=body, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_who_may_configure(client):
    t = team(client)
    assert_error(add(client, t["st"], t), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], True).status_code == 200  # wrong module
    assert_error(add(client, t["st"], t), 403, "MODULE_ACCESS_DENIED")
    grant(client, t)
    assert add(client, t["st"], t, times=["09:00"]).status_code == 201
    grant(client, t, granted=False)
    assert_error(add(client, t["st"], t, times=["10:00"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(add(client, t["dt"], t), 403, "FORBIDDEN")
    assert client.post(url(t), json={"times": ["08:00"]}).status_code == 401


def test_at_most_three_active_checks(client):
    t = team(client)
    assert add(client, t["pt"], t, times=["08:00", "14:00", "20:00"]).status_code == 201
    assert_error(add(client, t["pt"], t, times=["21:00"]), 409, "WELLNESS_LIMIT_REACHED")
    wc = client.get(url(t), headers=auth(t["pt"])).json()["items"][0]["wc_id"]
    assert client.delete(url(t, f"/{wc}"), headers=auth(t["pt"])).status_code == 204
    assert add(client, t["pt"], t, times=["21:00"]).status_code == 201  # a switched-off check frees a place


def test_a_time_that_already_exists_is_refused(client):
    t = team(client)
    add(client, t["pt"], t, times=["08:00"])
    r = add(client, t["pt"], t, times=["08:00", "09:00"])
    assert_error(r, 409, "WELLNESS_TIME_EXISTS")
    assert r.json()["error"]["details"]["times"] == ["08:00"]
    assert [i["time"] for i in client.get(url(t), headers=auth(t["pt"])).json()["items"]] == ["08:00"]  # nothing half-saved


def test_default_schedule_then_edit_it(client):
    t = team(client)
    r = client.post(url(t, "/default-schedule"), headers=auth(t["pt"]))
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    assert [i["time"] for i in items] == ["08:00", "14:00", "20:00"] and {i["grace_period_min"] for i in items} == {30}
    assert_error(client.post(url(t, "/default-schedule"), headers=auth(t["pt"])), 409, "SCHEDULE_ALREADY_EXISTS")
    assert_error(client.post(url(t, "/default-schedule"), headers=auth(t["dt"])), 403, "FORBIDDEN")
    r = client.put(url(t, f"/{items[0]['wc_id']}"), json={"time": "07:30", "grace_period_min": 45}, headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json()["time"] == "07:30" and r.json()["grace_period_min"] == 45


def test_reading_rules(client):
    t = team(client)
    add(client, t["pt"], t)
    assert len(client.get(url(t), headers=auth(t["pt"])).json()["items"]) == 1
    assert len(client.get(url(t), headers=auth(t["dt"])).json()["items"]) == 1
    assert_error(client.get(url(t), headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    other = other_dependent_token(client)
    assert_error(client.get(url(t), headers=auth(other)), 403, "FORBIDDEN")


def test_update_rules(client):
    t = team(client)
    items = add(client, t["pt"], t, times=["08:00", "20:00"]).json()["items"]
    a, b = items[0]["wc_id"], items[1]["wc_id"]
    h = auth(t["pt"])
    assert_error(client.put(url(t, f"/{a}"), json={"time": "20:00"}, headers=h), 409, "WELLNESS_TIME_EXISTS")
    assert_error(client.put(url(t, f"/{a}"), json={"grace_period_min": 1}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.put(url(t, f"/{a}"), json={"time": "nine"}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.put(url(t, f"/{uuid.uuid4()}"), json={"time": "09:00"}, headers=h), 404, "WELLNESS_CHECK_NOT_FOUND")
    assert_error(client.put(url(t, f"/{a}"), json={"time": "09:00"}, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.put(url(t, f"/{a}"), json={"time": "09:00"}, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert client.put(url(t, f"/{a}"), json={"active": False}, headers=h).json()["active"] is False
    assert client.put(url(t, f"/{a}"), json={"active": True}, headers=h).json()["active"] is True


def test_switching_off_hides_but_keeps_the_row(client, db):
    t = team(client)
    wc = add(client, t["pt"], t).json()["items"][0]["wc_id"]
    assert client.delete(url(t, f"/{wc}"), headers=auth(t["pt"])).status_code == 204
    assert client.delete(url(t, f"/{wc}"), headers=auth(t["pt"])).status_code == 204
    assert client.get(url(t), headers=auth(t["pt"])).json()["items"] == []
    assert len(client.get(url(t), params={"include_inactive": "true"}, headers=auth(t["pt"])).json()["items"]) == 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(WellnessCheckSchedule)) == 1


# ------------------------------------------------------------ prompts

def test_prompt_at_the_check_time(client, db):
    t = team(client)
    wc, due = mk(client, t)
    assert ws.tick(db, now=due - timedelta(minutes=1)) == 0  # not yet
    assert responses(db) == []
    assert ws.tick(db, now=due) == 1
    r = responses(db)[0]
    assert r.prompted_at == due and r.status == "pending"
    n = inbox(client, t["dt"])["items"]
    assert len(n) == 1 and (n[0]["type"], n[0]["priority"]) == ("wellness_check_prompt", "critical")
    assert n[0]["data"]["response_id"] == str(r.response_id) and n[0]["title"] == "Are you OK?"
    assert datetime.fromisoformat(n[0]["data"]["deadline"]) == due + GRACE
    assert ws.tick(db, now=due + timedelta(minutes=3)) == 0  # not twice
    assert len(responses(db)) == 1


def test_no_late_prompt_after_the_grace_period(client, db):
    t = team(client)
    wc, due = mk(client, t)
    assert ws.tick(db, now=due + GRACE + timedelta(minutes=1)) == 0
    assert responses(db) == []


def test_no_prompt_for_a_time_before_the_check_existed(client, db):
    t = team(client)
    hhmm, due = local_hhmm(-10)  # created now, for 10 minutes ago, still "inside" the grace period
    assert add(client, t["pt"], t, times=[hhmm]).status_code == 201
    assert ws.tick(db, now=datetime.now(timezone.utc)) == 0
    assert responses(db) == []


def test_switched_off_check_does_not_prompt(client, db):
    t = team(client)
    wc, due = mk(client, t)
    client.delete(url(t, f"/{wc}"), headers=auth(t["pt"]))
    assert ws.tick(db, now=due) == 0


def test_two_processes_prompt_once(client, db, engine):
    t = team(client)
    wc, due = mk(client, t)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return ws.tick(s, now=due)
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(run, range(6))) == 1
    assert len(responses(db)) == 1 and len(inbox(client, t["dt"])["items"]) == 1


def test_response_list(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    u = f"/dependents/{t['dep']}/wellness-check-responses"
    items = client.get(u, headers=auth(t["pt"]), params={"to": (due + timedelta(hours=1)).isoformat(), "from": (due - timedelta(hours=1)).isoformat()}).json()["items"]
    assert len(items) == 1 and items[0]["status"] == "pending" and items[0]["open_alert_tier"] is None
    assert datetime.fromisoformat(items[0]["deadline"]) == due + GRACE
    assert_error(client.get(u, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(u, params={"status": "bogus"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert client.get(u, headers=auth(t["dt"])).status_code == 200


# ------------------------------------------------------------ answering

def test_dependent_answers_and_repeat_keeps_first_time(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    a = respond(client, t["dt"], r.response_id)
    assert a.status_code == 200, a.text
    assert a.json()["status"] == "responded" and a.json()["already_responded"] is False
    b = respond(client, t["dt"], r.response_id).json()
    assert b["already_responded"] is True and b["responded_at"] == a.json()["responded_at"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "wellness_check_answered")) == 1


def test_only_the_dependent_can_answer(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    assert_error(respond(client, t["pt"], r.response_id), 403, "FORBIDDEN")
    assert_error(respond(client, t["st"], r.response_id), 403, "FORBIDDEN")
    assert client.post(f"/wellness-checks/{r.response_id}/respond").status_code == 401
    assert_error(respond(client, t["dt"], uuid.uuid4()), 404, "WELLNESS_CHECK_NOT_FOUND")
    other = other_dependent_token(client)
    assert_error(respond(client, other, r.response_id), 404, "WELLNESS_CHECK_NOT_FOUND")
    assert responses(db)[0].status == "pending"


def test_an_answered_check_is_never_escalated(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    respond(client, t["dt"], r.response_id)
    assert ws.sweep(db, now=due + GRACE + timedelta(hours=1)) == 0
    assert events(db) == []


# ------------------------------------------------------------ grace period, activity cross-check, escalation

def test_unanswered_with_no_activity_escalates_to_the_primary(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    assert ws.sweep(db, now=due + GRACE - timedelta(seconds=30)) == 0  # still inside the grace period
    assert responses(db)[0].status == "pending"
    assert ws.sweep(db, now=due + GRACE + timedelta(seconds=30)) == 1
    assert responses(db)[0].status == "escalated"
    ev = events(db)
    assert len(ev) == 1 and ev[0].tier == "primary" and ev[0].status == "open" and ev[0].reference_id == r.response_id
    assert ws.sweep(db, now=due + GRACE + timedelta(minutes=5)) == 0
    assert len(events(db)) == 1


def test_primary_is_alerted_secondary_is_not(client, db):
    t, wc, due, r = escalated(client, db)
    assert notification_service.dispatch_events(db) == 1
    n = inbox(client, t["pt"])["items"]
    assert len(n) == 1 and (n[0]["type"], n[0]["priority"]) == ("wellness_check", "critical")
    hhmm = due.astimezone(ws.tz()).strftime("%H:%M")
    assert n[0]["body"] == f"Test User has not answered the {hhmm} wellness check, and their phone shows no recent activity."
    assert n[0]["data"]["response_id"] == str(r.response_id) and n[0]["data"]["tier"] == "primary"
    assert inbox(client, t["st"])["items"] == []
    assert notification_service.dispatch_events(db) == 0


def test_recent_device_activity_stops_the_escalation(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    now = due + GRACE + timedelta(minutes=1)
    fix_at(db, t["dep"], now - timedelta(minutes=5))
    assert ws.sweep(db, now=now) == 0
    assert responses(db)[0].status == "device_active"
    assert events(db) == []


def test_old_device_activity_does_not_count(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    now = due + GRACE + timedelta(minutes=1)
    fix_at(db, t["dep"], now - timedelta(seconds=get_settings().WELLNESS_ACTIVITY_WINDOW_S + 300))
    assert ws.sweep(db, now=now) == 1
    assert responses(db)[0].status == "escalated"


def test_another_persons_activity_does_not_count(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    other = other_dependent_token(client)
    other_id = client.get("/auth/me", headers=auth(other)).json()["user_id"]
    now = due + GRACE + timedelta(minutes=1)
    fix_at(db, other_id, now - timedelta(minutes=1))
    assert ws.sweep(db, now=now) == 1


def test_late_answer_closes_the_alert_and_sends_all_clear(client, db):
    t, wc, due, r = escalated(client, db)
    notification_service.dispatch_events(db)
    items = client.get(f"/dependents/{t['dep']}/wellness-check-responses", headers=auth(t["pt"]),
                       params={"from": (due - timedelta(hours=1)).isoformat(), "to": (due + timedelta(hours=1)).isoformat()}).json()["items"]
    assert items[0]["status"] == "escalated" and items[0]["open_alert_tier"] == "primary"
    assert respond(client, t["dt"], r.response_id).json()["status"] == "responded"
    ev = events(db)
    assert ev[0].status == "resolved" and ev[0].resolved_at is not None
    clear = [n for n in inbox(client, t["pt"])["items"] if n["priority"] == "standard"]
    assert len(clear) == 1 and clear[0]["title"] == "Wellness check answered" and clear[0]["body"] == "Test User has confirmed they are OK."


def test_switched_off_or_very_old_check_is_closed_without_an_alert(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    db.execute(update(WellnessCheckSchedule).values(active=False))
    db.commit()
    assert ws.sweep(db, now=due + GRACE + timedelta(minutes=1)) == 0
    assert responses(db)[0].status == "cancelled" and events(db) == []


def test_a_check_found_unanswered_hours_later_is_closed_without_an_alert(client, db):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    late = due + GRACE + timedelta(seconds=get_settings().WELLNESS_ALERT_MAX_AGE_S + 3600)
    assert ws.sweep(db, now=late) == 0
    assert responses(db)[0].status == "cancelled" and events(db) == []


def test_simultaneous_sweeps_open_one_alert(client, db, engine):
    t = team(client)
    wc, due, r = prompted(client, db, t)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return ws.sweep(s, now=due + GRACE + timedelta(minutes=1))
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(run, range(6))) == 1
    assert len(events(db)) == 1


def test_an_answer_arriving_during_the_sweep_wins(client, db, engine, monkeypatch):
    import sqlalchemy

    t = team(client)
    wc, due, r = prompted(client, db, t)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    real_update = ws.update

    def sneaky(model):
        s2 = Session()
        s2.execute(sqlalchemy.update(WellnessCheckResponse).values(status="responded", responded_at=datetime.now(timezone.utc)))
        s2.commit()
        s2.close()
        return real_update(model)

    monkeypatch.setattr(ws, "update", sneaky)
    assert ws.sweep(db, now=due + GRACE + timedelta(minutes=1)) == 0
    assert responses(db)[0].status == "responded" and events(db) == []


def test_jobs_are_registered_in_the_right_order():
    names = [n for n, _ in JOBS]
    assert "wellness_tick" in names
    assert names.index("wellness_sweep") < names.index("notification_dispatch")
