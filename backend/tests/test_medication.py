"""
Task 3.2 tests: medication schedules, reminders, two-step confirmation (FR-F1).
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.scheduler import JOBS
from app.models import AuditLog, MedicationConfirmation, MedicationSchedule, Notification
from app.services import medication_service as ms
from app.services import push_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_permissions import put

BODY = {"drug_name": "Metformin", "dosage": "500 mg", "times": ["08:00"], "frequency": "daily"}


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p
    p.sent.clear()


def local_hhmm(minutes_ahead):
    """A clock time (HH:MM, local) a few minutes from the real now, plus its exact UTC moment."""
    due = (datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)).replace(second=0, microsecond=0)
    return due.astimezone(ms.tz()).strftime("%H:%M"), due


def add(client, token, dep, **over):
    return client.post(f"/dependents/{dep}/medications", json={**BODY, **over}, headers=auth(token))


def one(client, t, minutes_ahead=20, **over):
    """Create one schedule due `minutes_ahead` minutes from now. Returns (schedule_id, due_utc)."""
    hhmm, due = local_hhmm(minutes_ahead)
    r = add(client, t["pt"], t["dep"], times=[hhmm], **over)
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["schedule_id"], due


def notes(db, user_id, type=None):
    db.expire_all()
    q = select(Notification).where(Notification.user_id == user_id)
    if type:
        q = q.where(Notification.type == type)
    return db.scalars(q).all()


def dose_rows(db):
    db.expire_all()
    return db.scalars(select(MedicationConfirmation).order_by(MedicationConfirmation.scheduled_for)).all()


def dep_id(db, t):
    import uuid

    return uuid.UUID(t["dep"])


def other_dependent_token(client):
    """A second, fully activated Dependent (with their own Primary) and their login token."""
    from tests.test_linkage import PASSWORD, PHOTO, link, login, make_dependent, make_guardian

    pt2, _, _ = make_guardian(client, 2)
    dep2 = make_dependent(client, 2)
    k = client.post(
        f"/dependents/{dep2}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-1111111-1", "liveness_image": PHOTO}
    )
    assert k.json()["status"] == "verified"
    assert link(client, pt2, dep2).status_code == 201
    return login(client, "d2@link-test.com")[0]


def step1(client, t, sid, **body):
    return client.post(f"/medications/{sid}/confirm-request", json=body or None, headers=auth(t["dt"]))


def step2(client, token, sid, ctoken):
    return client.post(f"/medications/{sid}/confirm", json={"confirm_token": ctoken}, headers=auth(token))


def due_dose(client, db, t, sid, due):
    """Run the job so the dose exists, return it."""
    ms.tick(db, now=due - timedelta(minutes=10))
    rows = dose_rows(db)
    assert len(rows) == 1
    return rows[0]


# ------------------------------------------------------------ pure logic

def test_frequency_text_round_trip_and_day_matching():
    assert ms.encode_frequency("daily", None) == "daily"
    assert ms.encode_frequency("weekly", ["thu", "mon"]) == "weekly:mon,thu"  # always in week order
    assert ms.decode_frequency("weekly:mon,thu") == ("weekly", ["mon", "thu"])
    assert ms.decode_frequency("daily") == ("daily", None)
    from datetime import date

    monday = date(2026, 10, 12)
    assert ms.applies_on("weekly:mon,thu", monday)
    assert not ms.applies_on("weekly:mon,thu", monday + timedelta(days=1))
    assert ms.applies_on("daily", monday + timedelta(days=1))


def test_dose_time_is_local_time_in_utc():
    from datetime import date, time

    # 08:00 in Karachi (UTC+5) is 03:00 UTC.
    assert ms.occurrence(date(2026, 10, 12), time(8, 0)) == datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc)
    # 00:30 local is the evening before in UTC.
    assert ms.occurrence(date(2026, 10, 12), time(0, 30)) == datetime(2026, 10, 11, 19, 30, tzinfo=timezone.utc)


# ------------------------------------------------------------ creating schedules

def test_primary_creates_one_row_per_time_sorted_and_deduplicated(client):
    t = team(client)
    r = add(client, t["pt"], t["dep"], times=["20:00", "08:00", "08:00"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["timezone"] == "Asia/Karachi"
    assert [i["time"] for i in body["items"]] == ["08:00", "20:00"]
    i = body["items"][0]
    assert i["drug_name"] == "Metformin" and i["frequency"] == "daily" and i["days"] is None and i["active"] is True


def test_weekly_schedule_keeps_days_in_week_order(client):
    t = team(client)
    r = add(client, t["pt"], t["dep"], frequency="weekly", days=["thu", "mon"])
    assert r.status_code == 201
    assert r.json()["items"][0]["days"] == ["mon", "thu"]


@pytest.mark.parametrize(
    "over",
    [
        {"times": []},
        {"times": ["8:00"]},
        {"times": ["24:00"]},
        {"times": ["08:60"]},
        {"times": ["09:00"] * 1 + [f"1{i}:00" for i in range(6)]},  # more than 6
        {"drug_name": "   "},
        {"dosage": ""},
        {"frequency": "weekly"},  # no days
        {"frequency": "daily", "days": ["mon"]},
        {"frequency": "monthly"},
        {"frequency": "weekly", "days": ["funday"]},
    ],
)
def test_bad_schedules_are_rejected(client, over):
    t = team(client)
    assert_error(add(client, t["pt"], t["dep"], **over), 422, "VALIDATION_ERROR")


def test_names_are_trimmed(client):
    t = team(client)
    r = add(client, t["pt"], t["dep"], drug_name="  Vitamin   D  ", dosage=" 1  tablet ")
    assert r.json()["items"][0]["drug_name"] == "Vitamin D"
    assert r.json()["items"][0]["dosage"] == "1 tablet"


def test_who_may_create(client):
    t = team(client)
    # Secondary: default deny, then allowed by a grant, then denied again when revoked.
    assert_error(add(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    assert add(client, t["st"], t["dep"]).status_code == 201
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], False).status_code == 200
    assert_error(add(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    # The Dependent cannot write their own schedule; nobody without a token can.
    assert_error(add(client, t["dt"], t["dep"]), 403, "FORBIDDEN")
    assert client.post(f"/dependents/{t['dep']}/medications", json=BODY).status_code == 401


def test_a_grant_for_another_module_is_not_enough(client):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], True).status_code == 200
    assert_error(add(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")


def test_cap_on_active_dose_times(client, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "MEDICATION_MAX_ACTIVE_SCHEDULES", 3)
    assert add(client, t["pt"], t["dep"], times=["08:00", "12:00", "16:00"]).status_code == 201
    assert_error(add(client, t["pt"], t["dep"], times=["20:00"]), 409, "MEDICATION_LIMIT_REACHED")


# ------------------------------------------------------------ reading, changing, switching off

def test_reading_rules(client):
    t = team(client)
    add(client, t["pt"], t["dep"])
    url = f"/dependents/{t['dep']}/medications"
    assert len(client.get(url, headers=auth(t["pt"])).json()["items"]) == 1
    assert len(client.get(url, headers=auth(t["dt"])).json()["items"]) == 1  # the Dependent sees their own
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    put(client, t["pt"], t["dep"], "medication_management", t["sid"], True)
    assert client.get(url, headers=auth(t["st"])).status_code == 200


def test_another_dependent_cannot_read_these_schedules(client):
    t = team(client)
    add(client, t["pt"], t["dep"])
    other_token = other_dependent_token(client)
    assert_error(client.get(f"/dependents/{t['dep']}/medications", headers=auth(other_token)), 403, "FORBIDDEN")


def test_update_time_drops_prepared_future_dose(client, db):
    t = team(client)
    sid, due = one(client, t)
    ms.tick(db, now=due - timedelta(minutes=10))
    assert len(dose_rows(db)) == 1
    new_hhmm, _ = local_hhmm(300)
    r = client.put(f"/dependents/{t['dep']}/medications/{sid}", json={"time": new_hhmm}, headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json()["time"] == new_hhmm
    assert dose_rows(db) == []  # the old, not-yet-due dose is gone


def test_update_keeps_a_taken_dose(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    assert step2(client, t["dt"], sid, tok).status_code == 200
    r = client.put(f"/dependents/{t['dep']}/medications/{sid}", json={"active": False}, headers=auth(t["pt"]))
    assert r.status_code == 200
    assert [d.status for d in dose_rows(db)] == ["taken"]


def test_update_validation_and_rules(client):
    t = team(client)
    sid, _ = one(client, t)
    url = f"/dependents/{t['dep']}/medications/{sid}"
    h = auth(t["pt"])
    assert_error(client.put(url, json={"frequency": "weekly"}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.put(url, json={"days": ["mon"]}, headers=h), 422, "VALIDATION_ERROR")  # still daily
    assert_error(client.put(url, json={"time": "7pm"}, headers=h), 422, "VALIDATION_ERROR")
    r = client.put(url, json={"frequency": "weekly", "days": ["fri", "mon"], "dosage": "250 mg"}, headers=h)
    assert r.status_code == 200 and r.json()["days"] == ["mon", "fri"] and r.json()["dosage"] == "250 mg"
    r = client.put(url, json={"frequency": "daily"}, headers=h)
    assert r.status_code == 200 and r.json()["days"] is None
    assert_error(client.put(url, json={"dosage": "x"}, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.put(url, json={"dosage": "x"}, headers=auth(t["dt"])), 403, "FORBIDDEN")


def test_switching_off_hides_but_keeps_the_row(client, db):
    t = team(client)
    sid, _ = one(client, t)
    url = f"/dependents/{t['dep']}/medications"
    assert client.delete(f"{url}/{sid}", headers=auth(t["pt"])).status_code == 204
    assert client.delete(f"{url}/{sid}", headers=auth(t["pt"])).status_code == 204  # repeat is fine
    assert client.get(url, headers=auth(t["pt"])).json()["items"] == []
    items = client.get(url, params={"include_inactive": "true"}, headers=auth(t["pt"])).json()["items"]
    assert len(items) == 1 and items[0]["active"] is False
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(MedicationSchedule)) == 1


def test_schedule_of_another_dependent_is_not_found(client):
    import uuid

    t = team(client)
    one(client, t)

    assert_error(
        client.put(f"/dependents/{t['dep']}/medications/{uuid.uuid4()}", json={"dosage": "x"}, headers=auth(t["pt"])),
        404,
        "MEDICATION_NOT_FOUND",
    )
    assert_error(client.delete(f"/dependents/{t['dep']}/medications/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "MEDICATION_NOT_FOUND")


# ------------------------------------------------------------ reminders (the job)

def test_reminder_then_critical_alert_then_no_repeats(client, db):
    t = team(client)
    sid, due = one(client, t)
    me = dep_id(db, t)
    assert ms.tick(db, now=due - timedelta(minutes=10)) == 1
    n = notes(db, me)
    assert [(x.type, x.priority) for x in n] == [("medication_reminder", "standard")]
    assert n[0].payload["schedule_id"] == sid and n[0].payload["drug_name"] == "Metformin"
    assert ms.tick(db, now=due - timedelta(minutes=9)) == 0  # same minute-job again: nothing new
    assert ms.tick(db, now=due) == 1
    assert sorted(x.type for x in notes(db, me)) == ["medication_due", "medication_reminder"]
    assert [x.priority for x in notes(db, me, "medication_due")] == ["critical"]
    assert ms.tick(db, now=due + timedelta(minutes=5)) == 0
    assert len(dose_rows(db)) == 1


def test_nothing_before_the_reminder_time(client, db):
    t = team(client)
    sid, due = one(client, t, minutes_ahead=60)
    assert ms.tick(db, now=due - timedelta(minutes=30)) == 0
    assert dose_rows(db) == []


def test_confirmed_dose_gets_no_alert(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    assert step2(client, t["dt"], sid, tok).status_code == 200
    assert ms.tick(db, now=due) == 0
    assert [x.type for x in notes(db, dep_id(db, t))] == ["medication_reminder"]


def test_after_the_window_a_late_dose_is_prepared_but_nobody_is_alerted(client, db):
    t = team(client)
    sid, due = one(client, t)
    late = due + timedelta(seconds=get_settings().MEDICATION_WINDOW_S + 60)
    assert ms.tick(db, now=late) == 0
    rows = dose_rows(db)
    assert len(rows) == 1 and rows[0].status == "pending"  # Task 3.3 will mark and escalate it


def test_no_dose_for_a_time_before_the_schedule_existed(client, db):
    t = team(client)
    hhmm, due = local_hhmm(-120)  # created now, for a time two hours ago
    assert add(client, t["pt"], t["dep"], times=[hhmm]).status_code == 201
    ms.tick(db, now=datetime.now(timezone.utc))
    assert dose_rows(db) == []


def test_weekly_schedule_only_on_its_days(client, db):
    t = team(client)
    hhmm, due = local_hhmm(20)
    today = DAYS_ABBR[due.astimezone(ms.tz()).weekday()]
    other = DAYS_ABBR[(due.astimezone(ms.tz()).weekday() + 2) % 7]
    add(client, t["pt"], t["dep"], times=[hhmm], frequency="weekly", days=[other])
    ms.tick(db, now=due - timedelta(minutes=10))
    assert dose_rows(db) == []
    add(client, t["pt"], t["dep"], drug_name="Other", times=[hhmm], frequency="weekly", days=[today])
    ms.tick(db, now=due - timedelta(minutes=10))
    assert len(dose_rows(db)) == 1


DAYS_ABBR = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def test_switched_off_schedule_is_ignored(client, db):
    t = team(client)
    sid, due = one(client, t)
    client.delete(f"/dependents/{t['dep']}/medications/{sid}", headers=auth(t["pt"]))
    assert ms.tick(db, now=due - timedelta(minutes=10)) == 0
    assert dose_rows(db) == []


def test_two_processes_running_the_job_together_send_once(client, db, engine):
    t = team(client)
    sid, due = one(client, t)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(6)

    def run(_):
        s = Session()
        try:
            barrier.wait()
            return ms.tick(s, now=due - timedelta(minutes=10))
        finally:
            s.close()

    with ThreadPoolExecutor(6) as pool:
        total = sum(pool.map(run, range(6)))
    assert total == 1
    assert len(notes(db, dep_id(db, t))) == 1 and len(dose_rows(db)) == 1


def test_job_is_registered():
    assert "medication_tick" in [n for n, _ in JOBS]


# ------------------------------------------------------------ dose list

def test_dose_list_and_filters(client, db):
    t = team(client)
    sid, due = one(client, t)
    ms.tick(db, now=due - timedelta(minutes=10))
    url = f"/dependents/{t['dep']}/medication-doses"
    d = client.get(url, headers=auth(t["pt"])).json()["items"]
    assert len(d) == 1 and d[0]["status"] == "pending" and d[0]["drug_name"] == "Metformin"
    assert datetime.fromisoformat(d[0]["window_ends_at"]) == due + timedelta(seconds=get_settings().MEDICATION_WINDOW_S)
    assert client.get(url, params={"status": "taken"}, headers=auth(t["pt"])).json()["items"] == []
    assert len(client.get(url, headers=auth(t["dt"])).json()["items"]) == 1
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(url, params={"status": "bogus"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    far = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    assert_error(client.get(url, params={"to": far}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ two-step confirmation

def test_two_steps_mark_the_dose_taken(client, db):
    t = team(client)
    sid, due = one(client, t)
    dose = due_dose(client, db, t, sid, due)
    r1 = step1(client, t, sid)
    assert r1.status_code == 200, r1.text
    j = r1.json()
    assert j["confirmation_id"] == str(dose.confirmation_id) and j["expires_in_s"] == 120
    assert dose_rows(db)[0].status == "pending"  # step 1 alone changes nothing
    r2 = step2(client, t["dt"], sid, j["confirm_token"])
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "taken" and r2.json()["already_confirmed"] is False
    row = dose_rows(db)[0]
    assert row.status == "taken" and row.confirmed_at is not None
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "medication_dose_confirmed")) == 1


def test_second_confirm_keeps_the_first_time(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    a = step2(client, t["dt"], sid, tok).json()
    b = step2(client, t["dt"], sid, tok).json()
    assert b["already_confirmed"] is True and b["confirmed_at"] == a["confirmed_at"]
    assert_error(step1(client, t, sid, confirmation_id=a["confirmation_id"]), 409, "DOSE_ALREADY_CONFIRMED")


def test_step_one_with_nothing_due(client):
    t = team(client)
    sid, _ = one(client, t)  # no job has run, so no dose exists yet
    assert_error(step1(client, t, sid), 404, "NO_DOSE_DUE")


def test_only_the_dependent_can_confirm(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    assert_error(client.post(f"/medications/{sid}/confirm-request", headers=auth(t["pt"])), 403, "FORBIDDEN")
    assert_error(client.post(f"/medications/{sid}/confirm-request", headers=auth(t["st"])), 403, "FORBIDDEN")
    tok = step1(client, t, sid).json()["confirm_token"]
    assert_error(step2(client, t["pt"], sid, tok), 403, "FORBIDDEN")
    assert dose_rows(db)[0].status == "pending"
    assert client.post(f"/medications/{sid}/confirm-request").status_code == 401


def test_bad_tokens_are_rejected(client, db, monkeypatch):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    assert_error(step2(client, t["dt"], sid, "not-a-real-token"), 400, "CONFIRM_TOKEN_INVALID")
    # An ordinary login token must not work as a confirmation.
    assert_error(step2(client, t["dt"], sid, t["dt"]), 400, "CONFIRM_TOKEN_INVALID")
    monkeypatch.setattr(get_settings(), "MEDICATION_CONFIRM_TOKEN_S", -5)
    old = step1(client, t, sid).json()["confirm_token"]
    assert_error(step2(client, t["dt"], sid, old), 400, "CONFIRM_TOKEN_EXPIRED")
    assert dose_rows(db)[0].status == "pending"


def test_token_is_tied_to_one_schedule_and_one_person(client, db):
    t = team(client)
    sid, due = one(client, t)
    hhmm2, due2 = local_hhmm(20)
    sid2 = add(client, t["pt"], t["dep"], drug_name="Aspirin", times=[hhmm2]).json()["items"][0]["schedule_id"]
    ms.tick(db, now=due - timedelta(minutes=10))
    tok = step1(client, t, sid).json()["confirm_token"]
    # Presented for a different schedule of the same person: refused, nothing changes.
    r = step2(client, t["dt"], sid2, tok)
    assert r.status_code in (400, 404), r.text
    assert all(d.status == "pending" for d in dose_rows(db))
    # Another Dependent presenting this token: refused.
    other = other_dependent_token(client)
    assert step2(client, other, sid, tok).status_code in (400, 404)
    assert all(d.status == "pending" for d in dose_rows(db))


def test_another_dependent_cannot_start_a_confirmation(client, db):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    other = other_dependent_token(client)
    assert_error(client.post(f"/medications/{sid}/confirm-request", headers=auth(other)), 404, "MEDICATION_NOT_FOUND")


def test_late_confirmation_is_still_recorded(client, db):
    t = team(client)
    sid, due = one(client, t)
    ms.tick(db, now=due + timedelta(seconds=get_settings().MEDICATION_WINDOW_S + 60))
    tok = step1(client, t, sid).json()["confirm_token"]
    assert step2(client, t["dt"], sid, tok).json()["status"] == "taken"


def test_simultaneous_confirms_change_the_dose_once(client, db, engine):
    t = team(client)
    sid, due = one(client, t)
    due_dose(client, db, t, sid, due)
    tok = step1(client, t, sid).json()["confirm_token"]
    barrier = threading.Barrier(8)

    def run(_):
        barrier.wait()
        return step2(client, t["dt"], sid, tok).json()

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(run, range(8)))
    assert sorted(r["already_confirmed"] for r in results) == [False] + [True] * 7
    assert len({r["confirmed_at"] for r in results}) == 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "medication_dose_confirmed")) == 1
