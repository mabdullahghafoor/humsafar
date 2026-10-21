"""
Task 5.1 tests: appointment tracker and reminders (FR-G4).
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Appointment, AuditLog, Notification
from app.services import appointments_service, push_service
from tests.test_linkage import assert_error, auth, make_secondary
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_permissions import put


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p


def utcnow():
    return datetime.now(timezone.utc)


def at(**delta):
    return (utcnow() + timedelta(**delta)).replace(microsecond=0)


def plan(client, token, dep, when=None, provider="Dr. Ayesha Khan", **extra):
    when = when or at(days=2)
    return client.post(
        f"/dependents/{dep}/appointments",
        json={"provider_name": provider, "scheduled_at": when.isoformat(), **extra},
        headers=auth(token),
    )


def ok(r, status=201):
    assert r.status_code == status, r.text
    return r.json()


def alist(client, token, dep, **params):
    r = client.get(f"/dependents/{dep}/appointments", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def allow(client, t, granted=True):
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], granted).status_code == 200


def types(client, token, kind):
    return [n for n in inbox(client, token)["items"] if n["type"] == kind]


def count_notes(db, kind):
    return db.scalar(select(func.count()).select_from(Notification).where(Notification.type == kind))


# ------------------------------------------------------------ add, read, change, cancel, delete

def test_guardian_dependent_and_permitted_secondary_can_add(client):
    t = team(client)
    allow(client, t)
    a = ok(plan(client, t["pt"], t["dep"], provider="  Dr. A  ", notes="  bring reports  "))
    assert a["provider_name"] == "Dr. A" and a["notes"] == "bring reports" and a["status"] == "scheduled"
    assert a["is_upcoming"] is True and a["created_by_name"] == "Test User"
    ok(plan(client, t["dt"], t["dep"], at(days=3)))
    ok(plan(client, t["st"], t["dep"], at(days=4)))
    assert alist(client, t["dt"], t["dep"])["total"] == 3


def test_secondary_needs_health_records_for_every_appointment_endpoint(client):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"]))
    d, aid = t["dep"], a["appointment_id"]
    h = auth(t["st"])
    calls = [
        lambda: client.get(f"/dependents/{d}/appointments", headers=h),
        lambda: plan(client, t["st"], d, at(days=5)),
        lambda: client.get(f"/dependents/{d}/appointments/{aid}", headers=h),
        lambda: client.patch(f"/dependents/{d}/appointments/{aid}", json={"notes": "x"}, headers=h),
        lambda: client.post(f"/dependents/{d}/appointments/{aid}/cancel", headers=h),
        lambda: client.delete(f"/dependents/{d}/appointments/{aid}", headers=h),
    ]
    for c in calls:
        assert_error(c(), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    assert client.get(f"/dependents/{d}/appointments/{aid}", headers=h).status_code == 200
    allow(client, t, False)
    for c in calls:
        assert_error(c(), 403, "MODULE_ACCESS_DENIED")


def test_strangers_and_login_are_enforced(client):
    t = team(client)
    assert_error(client.get(f"/dependents/{t['dep']}/appointments"), 401, "NOT_AUTHENTICATED")
    assert_error(client.post(f"/dependents/{t['dep']}/appointments", json={}), 401, "NOT_AUTHENTICATED")
    assert_error(client.get(f"/dependents/{uuid.uuid4()}/appointments", headers=auth(t["pt"])), 403, "NOT_LINKED_TO_DEPENDENT")
    other_dep_tok = None
    from tests.test_records import stranger_dependent_token
    other_dep_tok, _ = stranger_dependent_token(client, 9)
    assert_error(client.get(f"/dependents/{t['dep']}/appointments", headers=auth(other_dep_tok)), 403, "FORBIDDEN")
    assert_error(plan(client, other_dep_tok, t["dep"]), 403, "FORBIDDEN")


def test_bad_input(client):
    t = team(client)
    h = auth(t["pt"])
    url = f"/dependents/{t['dep']}/appointments"
    good = at(days=2).isoformat()
    for body in (
        {}, {"provider_name": "", "scheduled_at": good}, {"provider_name": "   ", "scheduled_at": good},
        {"provider_name": "x" * 151, "scheduled_at": good}, {"provider_name": "Dr", "scheduled_at": "2026-12-01T10:00:00"},  # no time zone
        {"provider_name": "Dr", "scheduled_at": "tomorrow"}, {"provider_name": "Dr", "scheduled_at": good, "notes": "x" * 2001},
        {"provider_name": "Dr\x00", "scheduled_at": good}, {"provider_name": "Dr", "scheduled_at": good, "notes": "a\x00b"},
        {"provider_name": "Dr"},
    ):
        assert_error(client.post(url, json=body, headers=h), 422, "VALIDATION_ERROR")
    assert_error(plan(client, t["pt"], t["dep"], at(minutes=-5)), 422, "APPOINTMENT_IN_PAST")
    assert_error(plan(client, t["pt"], t["dep"], utcnow() - timedelta(days=3)), 422, "APPOINTMENT_IN_PAST")
    assert alist(client, t["pt"], t["dep"], when="all")["total"] == 0


def test_time_zones_are_respected(client):
    t = team(client)
    karachi = datetime.now(timezone(timedelta(hours=5))) + timedelta(days=2)
    a = ok(client.post(f"/dependents/{t['dep']}/appointments", json={"provider_name": "Dr", "scheduled_at": karachi.isoformat()}, headers=auth(t["pt"])))
    assert datetime.fromisoformat(a["scheduled_at"]) == karachi.replace(microsecond=karachi.microsecond)


def test_no_double_booking_of_the_same_appointment(client):
    t = team(client)
    when = at(days=2)
    ok(plan(client, t["pt"], t["dep"], when, provider="Dr. Khan"))
    assert_error(plan(client, t["pt"], t["dep"], when, provider="dr. khan"), 409, "APPOINTMENT_EXISTS")
    ok(plan(client, t["pt"], t["dep"], when, provider="Dr. Other"))  # same time, another doctor is allowed
    ok(plan(client, t["pt"], t["dep"], when + timedelta(hours=1), provider="Dr. Khan"))


def test_parallel_identical_requests_make_one_appointment(client):
    t = team(client)
    when = at(days=2)
    n = 6
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return plan(client, t["pt"], t["dep"], when).status_code

    with ThreadPoolExecutor(n) as ex:
        codes = sorted(ex.map(go, range(n)))
    assert codes == [201] + [409] * (n - 1)
    assert alist(client, t["pt"], t["dep"])["total"] == 1


def test_limit_of_open_appointments_even_in_parallel(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "APPOINTMENT_MAX_OPEN", 3)
    t = team(client)
    n = 7
    gate = Barrier(n)

    def go(i):
        gate.wait()
        return plan(client, t["pt"], t["dep"], at(days=2, hours=i)).status_code

    with ThreadPoolExecutor(n) as ex:
        codes = sorted(ex.map(go, range(n)))
    assert codes == [201] * 3 + [409] * 4
    assert alist(client, t["pt"], t["dep"])["total"] == 3
    assert_error(plan(client, t["pt"], t["dep"], at(days=9)), 409, "APPOINTMENTS_LIMIT")


def test_cancelled_and_past_ones_do_not_count_towards_the_limit(client, monkeypatch, db):
    monkeypatch.setattr(get_settings(), "APPOINTMENT_MAX_OPEN", 2)
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    ok(plan(client, t["pt"], t["dep"], at(days=3)))
    assert_error(plan(client, t["pt"], t["dep"], at(days=4)), 409, "APPOINTMENTS_LIMIT")
    client.post(f"/dependents/{t['dep']}/appointments/{a['appointment_id']}/cancel", headers=auth(t["pt"]))
    ok(plan(client, t["pt"], t["dep"], at(days=4)))


def test_list_upcoming_past_all_and_paging(client, db):
    t = team(client)
    ids = [ok(plan(client, t["pt"], t["dep"], at(days=d), provider=f"Dr {d}"))["appointment_id"] for d in (5, 2, 9, 3)]
    # an old one (the API refuses the past, so put it in directly) and a cancelled one
    old = Appointment(dependent_id=t["dep"], provider_name="Old", scheduled_at=at(days=-4), created_by=t["dep"], status="scheduled")
    db.add(old)
    db.commit()
    client.post(f"/dependents/{t['dep']}/appointments/{ids[2]}/cancel", headers=auth(t["pt"]))
    names = lambda **p: [i["provider_name"] for i in alist(client, t["pt"], t["dep"], **p)["items"]]
    assert names() == ["Dr 2", "Dr 3", "Dr 5"]  # upcoming, soonest first, no cancelled
    assert names(when="past") == ["Dr 9", "Old"]  # cancelled + already happened, latest first
    assert names(when="all") == ["Dr 9", "Dr 5", "Dr 3", "Dr 2", "Old"]
    p = alist(client, t["pt"], t["dep"], limit=2)
    assert p["total"] == 3 and len(p["items"]) == 2 and p["limit"] == 2 and p["offset"] == 0
    assert [i["provider_name"] for i in alist(client, t["pt"], t["dep"], limit=2, offset=2)["items"]] == ["Dr 5"]
    assert all(i["is_upcoming"] for i in alist(client, t["pt"], t["dep"])["items"])
    assert not any(i["is_upcoming"] for i in alist(client, t["pt"], t["dep"], when="past")["items"])
    assert_error(client.get(f"/dependents/{t['dep']}/appointments", params={"when": "later"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_get_one_and_isolation_between_dependents(client):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"]))
    assert ok(client.get(f"/dependents/{t['dep']}/appointments/{a['appointment_id']}", headers=auth(t["dt"])), 200)["provider_name"] == "Dr. Ayesha Khan"
    from tests.test_records import second_dependent
    dep2 = second_dependent(client, t)
    assert_error(client.get(f"/dependents/{dep2}/appointments/{a['appointment_id']}", headers=auth(t["pt"])), 404, "APPOINTMENT_NOT_FOUND")
    assert_error(client.delete(f"/dependents/{dep2}/appointments/{a['appointment_id']}", headers=auth(t["pt"])), 404, "APPOINTMENT_NOT_FOUND")
    assert_error(client.get(f"/dependents/{t['dep']}/appointments/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "APPOINTMENT_NOT_FOUND")


def test_change_cancel_and_delete(client, db):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], notes="old note"))
    url = f"/dependents/{t['dep']}/appointments/{a['appointment_id']}"
    h = auth(t["pt"])
    r = ok(client.patch(url, json={"provider_name": " City Clinic ", "notes": ""}, headers=h), 200)
    assert r["provider_name"] == "City Clinic" and r["notes"] is None and r["scheduled_at"] == a["scheduled_at"]
    new_time = at(days=6)
    assert datetime.fromisoformat(ok(client.patch(url, json={"scheduled_at": new_time.isoformat()}, headers=h), 200)["scheduled_at"]) == new_time
    assert_error(client.patch(url, json={}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"provider_name": None}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"scheduled_at": None}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"scheduled_at": at(hours=-1).isoformat()}, headers=h), 422, "APPOINTMENT_IN_PAST")
    c = ok(client.post(url + "/cancel", headers=h), 200)
    assert c["status"] == "cancelled" and c["is_upcoming"] is False
    assert ok(client.post(url + "/cancel", headers=h), 200)["status"] == "cancelled"  # repeat is fine
    assert_error(client.patch(url, json={"notes": "x"}, headers=h), 409, "APPOINTMENT_CANCELLED")
    assert client.delete(url, headers=h).status_code == 204
    assert_error(client.get(url, headers=h), 404, "APPOINTMENT_NOT_FOUND")
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"appointment_added", "appointment_changed", "appointment_cancelled", "appointment_deleted"} <= actions


def test_a_cancelled_appointment_does_not_block_booking_the_same_slot_again(client):
    t = team(client)
    when = at(days=2)
    a = ok(plan(client, t["pt"], t["dep"], when))
    client.post(f"/dependents/{t['dep']}/appointments/{a['appointment_id']}/cancel", headers=auth(t["pt"]))
    ok(plan(client, t["pt"], t["dep"], when))


# ------------------------------------------------------------ "something changed" messages

def test_others_are_told_when_one_is_added_moved_or_cancelled(client, db):
    t = team(client)
    allow(client, t)
    a = ok(plan(client, t["pt"], t["dep"]))
    # told: the Dependent and the permitted Secondary. Not told: the person who did it.
    d = types(client, t["dt"], "appointment_update")
    s = types(client, t["st"], "appointment_update")
    assert len(d) == 1 and len(s) == 1 and types(client, t["pt"], "appointment_update") == []
    assert d[0]["priority"] == "standard" and d[0]["title"] == "New appointment"
    assert "Your appointment with Dr. Ayesha Khan" in d[0]["body"] and "Test User's appointment" in s[0]["body"]
    assert d[0]["data"]["appointment_id"] == a["appointment_id"]
    url = f"/dependents/{t['dep']}/appointments/{a['appointment_id']}"
    client.patch(url, json={"notes": "only a note"}, headers=auth(t["pt"]))
    assert len(types(client, t["dt"], "appointment_update")) == 1  # a note change is not worth a message
    client.patch(url, json={"scheduled_at": at(days=7).isoformat()}, headers=auth(t["pt"]))
    assert [n["title"] for n in types(client, t["dt"], "appointment_update")] == ["Appointment moved", "New appointment"]
    client.post(url + "/cancel", headers=auth(t["dt"]))  # the Dependent cancels: the Primary and the Secondary hear about it, not the Dependent
    assert types(client, t["dt"], "appointment_update")[0]["title"] == "Appointment moved"
    assert types(client, t["pt"], "appointment_update")[0]["title"] == "Appointment cancelled"
    assert types(client, t["st"], "appointment_update")[0]["title"] == "Appointment cancelled"


def test_a_secondary_without_permission_is_never_told(client):
    t = team(client)
    ok(plan(client, t["pt"], t["dep"]))
    assert types(client, t["st"], "appointment_update") == []


def test_a_failed_push_does_not_lose_the_appointment(client, push):
    t = team(client)
    push.fail = True
    ok(plan(client, t["pt"], t["dep"]))
    assert alist(client, t["pt"], t["dep"])["total"] == 1 and len(types(client, t["dt"], "appointment_update")) == 1


# ------------------------------------------------------------ reminders

def reminders(client, token):
    return types(client, token, "appointment_reminder")


def test_reminders_24h_and_1h_to_dependent_primary_and_permitted_secondary(client, db):
    t = team(client)
    allow(client, t)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2), provider="Dr. Khan"))
    when = datetime.fromisoformat(a["scheduled_at"])
    assert appointments_service.tick(db, now=when - timedelta(hours=30)) == 0  # too early
    assert appointments_service.tick(db, now=when - timedelta(hours=23, minutes=59)) == 3
    assert appointments_service.tick(db, now=when - timedelta(hours=23)) == 0  # not twice
    for tok in (t["dt"], t["pt"], t["st"]):
        r = reminders(client, tok)
        assert len(r) == 1 and r[0]["priority"] == "standard" and r[0]["data"]["lead_s"] == 86400
    assert "You have an appointment with Dr. Khan" in reminders(client, t["dt"])[0]["body"]
    assert "has an appointment with Dr. Khan" in reminders(client, t["pt"])[0]["body"] and "Test User" in reminders(client, t["pt"])[0]["body"]
    assert appointments_service.tick(db, now=when - timedelta(minutes=59)) == 3
    assert appointments_service.tick(db, now=when - timedelta(minutes=10)) == 0
    assert [n["data"]["lead_s"] for n in reminders(client, t["dt"])] == [3600, 86400]
    assert appointments_service.tick(db, now=when + timedelta(minutes=1)) == 0  # nothing after the appointment time


def test_no_24h_reminder_for_an_appointment_made_at_short_notice(client, db):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(hours=3)))
    when = datetime.fromisoformat(a["scheduled_at"])
    assert appointments_service.tick(db, now=utcnow()) == 0  # the 24 h point had passed before it was made
    assert appointments_service.tick(db, now=when - timedelta(minutes=59)) == 2  # Dependent + Primary, the 1 h reminder
    assert [n["data"]["lead_s"] for n in reminders(client, t["dt"])] == [3600]


def test_after_downtime_only_the_closest_reminder_is_sent(client, db):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    when = datetime.fromisoformat(a["scheduled_at"])
    assert appointments_service.tick(db, now=when - timedelta(minutes=10)) == 2
    assert [n["data"]["lead_s"] for n in reminders(client, t["dt"])] == [3600]


def test_moving_an_appointment_gives_new_reminders(client, db):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    when = datetime.fromisoformat(a["scheduled_at"])
    assert appointments_service.tick(db, now=when - timedelta(hours=23)) == 2
    new = at(days=5)
    client.patch(f"/dependents/{t['dep']}/appointments/{a['appointment_id']}", json={"scheduled_at": new.isoformat()}, headers=auth(t["pt"]))
    assert appointments_service.tick(db, now=when - timedelta(hours=22)) == 0  # the old time no longer matters
    assert appointments_service.tick(db, now=new - timedelta(hours=23)) == 2
    assert len(reminders(client, t["dt"])) == 2


def test_cancelled_deleted_and_past_get_no_reminder(client, db):
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2), provider="A"))
    b = ok(plan(client, t["pt"], t["dep"], at(days=2, hours=1), provider="B"))
    c = ok(plan(client, t["pt"], t["dep"], at(days=2, hours=2), provider="C"))
    base = f"/dependents/{t['dep']}/appointments"
    client.post(f"{base}/{a['appointment_id']}/cancel", headers=auth(t["pt"]))
    client.delete(f"{base}/{b['appointment_id']}", headers=auth(t["pt"]))
    when_c = datetime.fromisoformat(c["scheduled_at"])
    assert appointments_service.tick(db, now=when_c - timedelta(hours=23, minutes=30)) == 2  # only C
    assert {n["data"]["provider_name"] for n in reminders(client, t["dt"])} == {"C"}
    assert appointments_service.tick(db, now=when_c + timedelta(hours=1)) == 0


def test_secondary_loses_reminders_when_permission_is_removed(client, db):
    t = team(client)
    allow(client, t)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    allow(client, t, False)
    assert appointments_service.tick(db, now=datetime.fromisoformat(a["scheduled_at"]) - timedelta(hours=23)) == 2
    assert reminders(client, t["st"]) == []


def test_unverified_secondary_gets_no_reminder(client, db):
    t = team(client)
    st2, sid2, _ = make_secondary(client, t["pt"], t["dep"], 2)  # not verified
    assert put(client, t["pt"], t["dep"], "health_records", sid2, True).status_code == 200
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    assert appointments_service.tick(db, now=datetime.fromisoformat(a["scheduled_at"]) - timedelta(hours=23)) == 2
    assert reminders(client, st2) == []


def test_two_servers_running_the_job_together_send_each_reminder_once(client, db, engine):
    t = team(client)
    allow(client, t)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    now = datetime.fromisoformat(a["scheduled_at"]) - timedelta(hours=23)
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    n = 4
    gate = Barrier(n)

    def go(_):
        gate.wait()
        s = SessionLocal()
        try:
            return appointments_service.tick(s, now=now)
        finally:
            s.close()

    with ThreadPoolExecutor(n) as ex:
        assert sum(ex.map(go, range(n))) == 3
    assert count_notes(db, "appointment_reminder") == 3


def test_reminder_leads_are_configurable_and_bad_values_ignored(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "APPOINTMENT_REMIND_LEADS_S", " 7200 , abc, -5, 0, 7200 ")
    t = team(client)
    a = ok(plan(client, t["pt"], t["dep"], at(days=2)))
    when = datetime.fromisoformat(a["scheduled_at"])
    assert appointments_service.tick(db, now=when - timedelta(hours=23)) == 0
    assert appointments_service.tick(db, now=when - timedelta(hours=1, minutes=59)) == 2
    monkeypatch.setattr(get_settings(), "APPOINTMENT_REMIND_LEADS_S", "")
    assert appointments_service.tick(db, now=when - timedelta(minutes=5)) == 0


def test_the_job_is_registered_with_the_scheduler():
    from app.core import scheduler
    assert "appointment_tick" in [n for n, _ in scheduler.JOBS]
