"""
Task 3.3 tests: missed-dose escalation (FR-D1): detection, alert, extend, escalate, late confirmation.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.scheduler import JOBS
from app.models import AuditLog, EscalationEvent, MedicationConfirmation, MedicationSchedule, Notification
from app.services import medication_service as ms
from app.services import notification_service, push_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_medication import dep_id, due_dose, notes, one, step1, step2
from tests.test_notifications import inbox
from tests.test_permissions import put

WINDOW = timedelta(seconds=get_settings().MEDICATION_WINDOW_S)


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()


def events(db, **where):
    db.expire_all()
    q = select(EscalationEvent).where(EscalationEvent.trigger_type == "missed_dose")
    for k, v in where.items():
        q = q.where(getattr(EscalationEvent, k) == v)
    return db.scalars(q.order_by(EscalationEvent.created_at)).all()


def missed_setup(client, db):
    """A dose that is past its window and has been swept: returns (team, schedule_id, due, dose)."""
    t = team(client)
    sid, due = one(client, t)
    dose = due_dose(client, db, t, sid, due)
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(minutes=1)) == 1
    return t, sid, due, dose


def doses_url(t):
    return f"/dependents/{t['dep']}/medication-doses"


def grant(client, t, module, granted=True):
    assert put(client, t["pt"], t["dep"], module, t["sid"], granted).status_code == 200


def types(client, token, **p):
    return [(n["type"], n["priority"]) for n in inbox(client, token, **p)["items"]]


# ------------------------------------------------------------ detecting a missed dose

def test_dose_becomes_missed_only_after_its_window(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    assert ms.sweep_missed(db, now=due + WINDOW - timedelta(seconds=30)) == 0
    assert [d.status for d in db.scalars(select(MedicationConfirmation)).all()] == ["pending"]
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(seconds=30)) == 1
    db.expire_all()
    assert [d.status for d in db.scalars(select(MedicationConfirmation)).all()] == ["missed"]
    ev = events(db)
    assert len(ev) == 1 and ev[0].tier == "primary" and ev[0].status == "open"


def test_sweeping_again_changes_nothing(client, db):
    t, sid, due, dose = missed_setup(client, db)
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(minutes=5)) == 0
    assert len(events(db)) == 1


def test_a_taken_dose_is_never_missed(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    assert step2(client, t["dt"], sid, tok).status_code == 200
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(hours=1)) == 0
    assert events(db) == []


def test_switched_off_schedule_is_marked_but_not_alerted(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    db.execute(update(MedicationSchedule).values(active=False))
    db.commit()
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(minutes=1)) == 0
    db.expire_all()
    assert db.scalars(select(MedicationConfirmation.status)).all() == ["missed"]
    assert events(db) == []


def test_a_very_old_miss_is_marked_but_not_alerted(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    old = due + WINDOW + timedelta(seconds=get_settings().MEDICATION_MISSED_ALERT_MAX_AGE_S + 3600)
    assert ms.sweep_missed(db, now=old) == 0
    db.expire_all()
    assert db.scalars(select(MedicationConfirmation.status)).all() == ["missed"]
    assert events(db) == []


def test_simultaneous_sweeps_open_one_alert(client, db, engine):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return ms.sweep_missed(s, now=due + WINDOW + timedelta(minutes=1))
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(run, range(6))) == 1
    assert len(events(db)) == 1


def test_a_confirmation_arriving_during_the_sweep_wins(client, db, engine, monkeypatch):
    import sqlalchemy

    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    real_update = ms.update

    def sneaky(model):
        # The Dependent confirms in the instant after the sweep looked, before it changed the dose.
        s2 = Session()
        s2.execute(sqlalchemy.update(MedicationConfirmation).values(status="taken"))
        s2.commit()
        s2.close()
        return real_update(model)

    monkeypatch.setattr(ms, "update", sneaky)
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(minutes=1)) == 0
    db.expire_all()
    assert db.scalars(select(MedicationConfirmation.status)).all() == ["taken"]
    assert events(db) == []


def test_sweep_runs_before_the_dispatch_in_the_job_list():
    names = [n for n, _ in JOBS]
    assert names.index("medication_missed_sweep") < names.index("notification_dispatch")


# ------------------------------------------------------------ who is told

def test_primary_is_alerted_with_the_drug_and_time(client, db):
    t, sid, due, dose = missed_setup(client, db)
    assert notification_service.dispatch_events(db) == 1
    items = inbox(client, t["pt"])["items"]
    assert len(items) == 1
    n = items[0]
    assert (n["type"], n["priority"]) == ("missed_dose", "critical")
    hhmm = due.astimezone(ms.tz()).strftime("%H:%M")
    assert n["body"] == f"Test User has not taken Metformin (500 mg) due at {hhmm}."
    assert n["data"]["confirmation_id"] == str(dose.confirmation_id) and n["data"]["tier"] == "primary"
    assert n["event_id"] == str(events(db)[0].event_id)
    # Not the Secondary (still at the Primary level), not the Dependent.
    assert inbox(client, t["st"])["items"] == []
    assert [x for x in types(client, t["dt"]) if x[0] == "missed_dose"] == []


def test_dispatch_twice_alerts_once(client, db):
    t, *_ = missed_setup(client, db)
    assert notification_service.dispatch_events(db) == 1
    assert notification_service.dispatch_events(db) == 0
    assert len(inbox(client, t["pt"])["items"]) == 1


def test_dose_list_shows_the_open_alert_tier(client, db):
    t, sid, due, dose = missed_setup(client, db)
    items = client.get(doses_url(t), params={"from": (due - timedelta(hours=1)).isoformat()}, headers=auth(t["pt"])).json()["items"]
    assert items[0]["status"] == "missed" and items[0]["open_alert_tier"] == "primary"


# ------------------------------------------------------------ taking it late

def test_late_confirmation_closes_the_alert_and_sends_all_clear(client, db):
    t, sid, due, dose = missed_setup(client, db)
    notification_service.dispatch_events(db)
    tok = step1(client, t, sid).json()["confirm_token"]
    r = step2(client, t["dt"], sid, tok)
    assert r.status_code == 200 and r.json()["status"] == "taken"
    ev = events(db)
    assert len(ev) == 1 and ev[0].status == "resolved" and ev[0].resolved_at is not None
    got = inbox(client, t["pt"])["items"]
    clear = [n for n in got if n["priority"] == "standard"]
    assert len(clear) == 1
    assert clear[0]["title"] == "Missed dose closed" and clear[0]["body"] == "Test User took Metformin (500 mg) late."


# ------------------------------------------------------------ option 1: extend

def test_extend_a_missed_dose(client, db):
    t, sid, due, dose = missed_setup(client, db)
    notification_service.dispatch_events(db)
    r = client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", json={"minutes": 30}, headers=auth(t["pt"]))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "pending"
    # (the test clock is ahead of the real one, so the old deadline is still in the future: 30 min after it)
    assert datetime.fromisoformat(j["window_ends_at"]) == due + WINDOW + timedelta(minutes=30)
    assert j["open_alert_tier"] is None
    assert events(db)[0].status == "resolved"
    # Dependent: a critical "more time" alert. Primary: the all-clear.
    assert ("medication_extended", "critical") in types(client, t["dt"])
    clear = [n for n in inbox(client, t["pt"])["items"] if n["priority"] == "standard"]
    assert len(clear) == 1 and clear[0]["body"] == "Test User was given more time for Metformin (500 mg)."


def test_extending_after_the_deadline_counts_from_now(client, db):
    t, sid, due, dose = missed_setup(client, db)
    # Make the dose really old: it was due 3 hours ago.
    db.execute(update(MedicationConfirmation).values(scheduled_for=datetime.now(timezone.utc) - timedelta(hours=3)))
    db.commit()
    before = datetime.now(timezone.utc)
    r = client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", json={"minutes": 45}, headers=auth(t["pt"]))
    assert r.status_code == 200
    new_end = datetime.fromisoformat(r.json()["window_ends_at"])
    assert before + timedelta(minutes=44) < new_end < before + timedelta(minutes=46)


def test_extended_dose_can_be_missed_again_with_a_new_alert(client, db):
    t, sid, due, dose = missed_setup(client, db)
    notification_service.dispatch_events(db)
    j = client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", json={"minutes": 30}, headers=auth(t["pt"])).json()
    new_end = datetime.fromisoformat(j["window_ends_at"])
    assert ms.sweep_missed(db, now=new_end - timedelta(seconds=30)) == 0  # still inside the extra time
    assert ms.sweep_missed(db, now=new_end + timedelta(seconds=30)) == 1
    ev = events(db)
    assert [e.status for e in ev] == ["resolved", "open"] and ev[0].event_id != ev[1].event_id
    notification_service.dispatch_events(db)
    assert [n["type"] for n in inbox(client, t["pt"], priority="critical")["items"]] == ["missed_dose", "missed_dose"]


def test_extend_a_pending_dose_before_it_is_missed(client, db):
    t = team(client)
    sid, due = one(client, t)
    dose = due_dose(client, db, t, sid, due)
    r = client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", json={"minutes": 10}, headers=auth(t["pt"]))
    assert r.status_code == 200
    # 10 minutes AFTER the normal deadline, not 10 minutes from now.
    assert datetime.fromisoformat(r.json()["window_ends_at"]) == due + WINDOW + timedelta(minutes=10)
    assert ms.sweep_missed(db, now=due + WINDOW + timedelta(minutes=5)) == 0
    assert events(db) == []


def test_extend_default_is_30_minutes_and_rules(client, db):
    t, sid, due, dose = missed_setup(client, db)
    url = f"{doses_url(t)}/{dose.confirmation_id}/extend"
    for bad in (1, 4, 121, 500, 0, -5):
        assert_error(client.post(url, json={"minutes": bad}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert client.post(url, headers=auth(t["pt"])).status_code == 200  # no body: default
    assert_error(client.post(f"{doses_url(t)}/00000000-0000-0000-0000-000000000000/extend", headers=auth(t["pt"])), 404, "DOSE_NOT_FOUND")


def test_cannot_extend_a_taken_dose(client, db):
    t = team(client)
    sid, due = one(client, t)
    dose = due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    step2(client, t["dt"], sid, tok)
    assert_error(client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", headers=auth(t["pt"])), 409, "DOSE_ALREADY_CONFIRMED")


def test_who_may_extend_and_escalate(client, db):
    t, sid, due, dose = missed_setup(client, db)
    ext = f"{doses_url(t)}/{dose.confirmation_id}/extend"
    esc = f"{doses_url(t)}/{dose.confirmation_id}/escalate"
    assert_error(client.post(ext, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.post(esc, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.post(ext, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert_error(client.post(esc, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert client.post(ext).status_code == 401
    grant(client, t, "medication_management")
    assert client.post(ext, headers=auth(t["st"])).status_code == 200


def test_a_dose_of_another_dependent_is_not_reachable(client, db):
    from tests.test_medication import other_dependent_token

    t, sid, due, dose = missed_setup(client, db)
    other = other_dependent_token(client)
    # the other Dependent's own id in the path, this dose's id: not found, never leaked
    me = client.get("/auth/me", headers=auth(other)).json()["user_id"]
    assert_error(client.post(f"/dependents/{me}/medication-doses/{dose.confirmation_id}/extend", headers=auth(t["pt"])), 403, "NOT_LINKED_TO_DEPENDENT")


# ------------------------------------------------------------ option 2: escalate

def test_escalate_alerts_the_allowed_secondary(client, db):
    t, sid, due, dose = missed_setup(client, db)
    grant(client, t, "emergency_alerts")
    notification_service.dispatch_events(db)
    assert inbox(client, t["st"])["items"] == []  # Primary level only so far
    r = client.post(f"{doses_url(t)}/{dose.confirmation_id}/escalate", headers=auth(t["pt"]))
    assert r.status_code == 200, r.text
    assert r.json()["tier"] == "secondary" and r.json()["notified"] == 1
    got = inbox(client, t["st"])["items"]
    assert len(got) == 1 and got[0]["type"] == "missed_dose" and got[0]["priority"] == "critical" and got[0]["data"]["tier"] == "secondary"
    assert events(db)[0].tier == "secondary"
    items = client.get(doses_url(t), params={"from": (due - timedelta(hours=1)).isoformat()}, headers=auth(t["pt"])).json()["items"]
    assert items[0]["open_alert_tier"] == "secondary"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "medication_alert_escalated")) == 1


def test_escalate_with_no_allowed_secondary_notifies_nobody(client, db):
    t, sid, due, dose = missed_setup(client, db)  # Secondary has no emergency_alerts grant
    r = client.post(f"{doses_url(t)}/{dose.confirmation_id}/escalate", headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json()["notified"] == 0
    assert inbox(client, t["st"])["items"] == []


def test_cannot_escalate_twice_or_without_an_alert(client, db):
    t, sid, due, dose = missed_setup(client, db)
    url = f"{doses_url(t)}/{dose.confirmation_id}/escalate"
    assert client.post(url, headers=auth(t["pt"])).status_code == 200
    assert_error(client.post(url, headers=auth(t["pt"])), 409, "ALREADY_ESCALATED")
    # A dose that is not missed has no alert.
    client.post(f"{doses_url(t)}/{dose.confirmation_id}/extend", headers=auth(t["pt"]))
    assert_error(client.post(url, headers=auth(t["pt"])), 409, "NO_OPEN_ALERT")


def test_simultaneous_escalations_move_the_alert_once(client, db):
    t, sid, due, dose = missed_setup(client, db)
    grant(client, t, "emergency_alerts")
    url = f"{doses_url(t)}/{dose.confirmation_id}/escalate"
    barrier = threading.Barrier(6)

    def run(_):
        barrier.wait()
        return client.post(url, headers=auth(t["pt"])).status_code

    with ThreadPoolExecutor(6) as pool:
        codes = sorted(pool.map(run, range(6)))
    assert codes == [200] + [409] * 5
    assert len(inbox(client, t["st"])["items"]) == 1


def test_late_confirmation_after_escalation_closes_it_for_everyone_told(client, db):
    t, sid, due, dose = missed_setup(client, db)
    grant(client, t, "emergency_alerts")
    notification_service.dispatch_events(db)  # the Primary is told first
    client.post(f"{doses_url(t)}/{dose.confirmation_id}/escalate", headers=auth(t["pt"]))
    tok = step1(client, t, sid).json()["confirm_token"]
    assert step2(client, t["dt"], sid, tok).status_code == 200
    for who in ("pt", "st"):
        clear = [n for n in inbox(client, t[who])["items"] if n["priority"] == "standard"]
        assert len(clear) == 1 and "took Metformin (500 mg) late" in clear[0]["body"]
