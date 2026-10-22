"""
Task 7.2 tests: automatic summary reports (FR-Q2): schedule, background job, manual report, PDF, access.
"""

import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.scheduler import JOBS
from app.models import AuditLog, ReportSchedule, SummaryReport
from app.services import analytics_service, medication_service as ms, report_service, retention_service
from tests.test_analytics import dose, local_today, reading, sched
from tests.test_linkage import assert_error, auth, make_dependent
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_permissions import put
from tests.test_retention import close_dep, make_due


@pytest.fixture(autouse=True)
def reports_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "REPORTS_STORAGE_DIR", str(tmp_path / "reports"))
    return tmp_path / "reports"


def files(d):
    return sorted(p for p in d.glob("*") if p.is_file()) if d.exists() else []


def make(client, token, dep, **body):
    return client.post(f"/dependents/{dep}/reports", json=body or None, headers=auth(token))


def listing(client, token, dep, **params):
    r = client.get(f"/dependents/{dep}/reports", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def download(client, token, dep, rid):
    return client.get(f"/dependents/{dep}/reports/{rid}/download", headers=auth(token))


def text_of(resp) -> str:
    assert resp.status_code == 200, resp.text
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(resp.content)).pages)


def put_schedule(client, token, dep, frequency="weekly"):
    return client.put(f"/dependents/{dep}/reports/schedule", json={"frequency": frequency}, headers=auth(token))


def days_ago(d):
    return (local_today() - d).days


def old_schedule(db, guardian_id, dep, frequency="weekly", days=40):
    """A schedule that was switched on `days` days ago, so earlier periods count."""
    db.execute(text("UPDATE report_schedules SET created_at = :c WHERE guardian_id = :g AND dependent_id = :d"),
               {"c": datetime.now(timezone.utc) - timedelta(days=days), "g": str(guardian_id), "d": str(dep)})
    db.commit()


def primary_id(client, t):
    return uuid.UUID(client.get("/auth/me", headers=auth(t["pt"])).json()["user_id"])


def data_in_last_week(client, db, t):
    first, last = report_service.last_week(local_today())
    s = sched(client, t)
    dose(db, s, ms.occurrence(first + timedelta(days=1), datetime.min.time().replace(hour=8)), "taken")
    dose(db, s, ms.occurrence(first + timedelta(days=2), datetime.min.time().replace(hour=8)), "missed")
    reading(db, t["dep"], "spo2", 97, ms.occurrence(first + timedelta(days=3), datetime.min.time().replace(hour=9)))
    return first, last


# ------------------------------------------------------------ structure

def test_the_job_is_registered():
    assert "summary_report_sweep" in [n for n, _ in JOBS]


def test_week_and_month_boundaries():
    # Wednesday 21 Oct 2026: the last finished week is Mon 12 - Sun 18 Oct, the last month September
    from datetime import date
    assert report_service.last_week(date(2026, 10, 21)) == (date(2026, 10, 12), date(2026, 10, 18))
    assert report_service.last_week(date(2026, 10, 19)) == (date(2026, 10, 12), date(2026, 10, 18))  # Monday: the week that just ended
    assert report_service.last_week(date(2026, 10, 18)) == (date(2026, 10, 5), date(2026, 10, 11))  # Sunday: the week is not over yet
    assert report_service.last_month(date(2026, 10, 21)) == (date(2026, 9, 1), date(2026, 9, 30))
    assert report_service.last_month(date(2026, 1, 1)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert report_service.last_month(date(2026, 3, 31)) == (date(2026, 2, 1), date(2026, 2, 28))


# ------------------------------------------------------------ who may do what

def test_only_guardians_with_permission(client):
    t = team(client)
    dep = t["dep"]
    for call in (lambda: make(client, t["dt"], dep), lambda: listing_raw(client, t["dt"], dep), lambda: put_schedule(client, t["dt"], dep)):
        assert_error(call(), 403, "FORBIDDEN")  # the Dependent
    assert client.get(f"/dependents/{dep}/reports").status_code == 401
    assert_error(make(client, t["st"], dep), 403, "MODULE_ACCESS_DENIED")  # a Secondary without any permission
    assert_error(put_schedule(client, t["st"], dep), 403, "MODULE_ACCESS_DENIED")
    other = make_dependent(client, 2)
    assert_error(make(client, t["pt"], other), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(listing_raw(client, t["pt"], other), 403, "NOT_LINKED_TO_DEPENDENT")


def listing_raw(client, token, dep):
    return client.get(f"/dependents/{dep}/reports", headers=auth(token))


# ------------------------------------------------------------ manual report and the PDF

def test_make_a_report_read_it_and_download_the_pdf(client, db, reports_dir):
    t = team(client)
    s = sched(client, t, "Metformin", "500 mg")
    dose(db, s, ms.occurrence(local_today() - timedelta(days=1), datetime.min.time().replace(hour=8)), "taken")
    reading(db, t["dep"], "blood_pressure", 120, datetime.now(timezone.utc) - timedelta(hours=30), diastolic=80)
    reading(db, t["dep"], "blood_pressure", 140, datetime.now(timezone.utc) - timedelta(hours=3), diastolic=90)
    r = make(client, t["pt"], t["dep"], days=14)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["period"] == "custom" and rep["source"] == "manual" and rep["includes_adherence"] and rep["includes_vitals"]
    assert rep["period_end"] == str(local_today()) and rep["period_start"] == str(local_today() - timedelta(days=13))
    assert rep["file_name"] == f"humsafar-summary-{rep['period_start']}-to-{rep['period_end']}.pdf" and rep["size_bytes"] > 1000

    got = listing(client, t["pt"], t["dep"])
    assert got["total"] == 1 and got["items"][0]["report_id"] == rep["report_id"]

    d = download(client, t["pt"], t["dep"], rep["report_id"])
    assert d.status_code == 200 and d.headers["content-type"] == "application/pdf" and d.content.startswith(b"%PDF-")
    assert "attachment" in d.headers["content-disposition"] and rep["file_name"] in d.headers["content-disposition"]
    assert "no-store" in d.headers["cache-control"]
    body = text_of(d)
    for word in ("Custom health summary", "Medicine adherence", "Metformin", "Vitals", "Blood pressure", "130/85", "not medical advice"):
        assert word in body, word

    # the stored file is encrypted, never a readable PDF
    stored = files(reports_dir)
    assert len(stored) == 1 and not stored[0].read_bytes().startswith(b"%PDF-")
    actions = [a for a in db.scalars(select(AuditLog.action).where(AuditLog.dependent_id == uuid.UUID(t["dep"])))]
    assert "summary_report_created" in actions and "summary_report_downloaded" in actions


def test_default_period_is_seven_days_and_days_are_limited(client):
    t = team(client)
    rep = make(client, t["pt"], t["dep"]).json()
    assert rep["period_start"] == str(local_today() - timedelta(days=6))
    for bad in (6, 91, 0, -1):
        assert_error(make(client, t["pt"], t["dep"], days=bad), 422, "VALIDATION_ERROR")
    assert make(client, t["pt"], t["dep"], days=90).status_code == 201


def test_an_empty_period_still_gives_a_clear_report(client):
    t = team(client)
    rep = make(client, t["pt"], t["dep"]).json()
    body = text_of(download(client, t["pt"], t["dep"], rep["report_id"]))
    assert "No medicine dose was decided in this period." in body and "No reading was saved in this period." in body


def test_sections_follow_the_permissions_and_download_rechecks_them(client, db):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    rep = make(client, t["st"], t["dep"]).json()
    assert rep["includes_adherence"] and not rep["includes_vitals"]
    body = text_of(download(client, t["st"], t["dep"], rep["report_id"]))
    assert "Medicine adherence" in body and "Vitals" not in body
    # the permission is taken away: the old report cannot be opened any more
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], False).status_code == 200
    assert_error(download(client, t["st"], t["dep"], rep["report_id"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(listing_raw(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    # vitals only
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], True).status_code == 200
    v = make(client, t["st"], t["dep"]).json()
    assert v["includes_vitals"] and not v["includes_adherence"]
    assert_error(download(client, t["st"], t["dep"], rep["report_id"]), 403, "MODULE_ACCESS_DENIED")  # still the adherence-only one


def test_a_report_belongs_to_the_guardian_who_made_it(client):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    mine = make(client, t["pt"], t["dep"]).json()
    theirs = make(client, t["st"], t["dep"]).json()
    assert [i["report_id"] for i in listing(client, t["pt"], t["dep"])["items"]] == [mine["report_id"]]
    assert [i["report_id"] for i in listing(client, t["st"], t["dep"])["items"]] == [theirs["report_id"]]
    assert_error(download(client, t["st"], t["dep"], mine["report_id"]), 404, "REPORT_NOT_FOUND")
    assert_error(client.delete(f"/dependents/{t['dep']}/reports/{mine['report_id']}", headers=auth(t["st"])), 404, "REPORT_NOT_FOUND")
    other = make_dependent(client, 2)
    assert_error(download(client, t["pt"], other, mine["report_id"]), 404, "REPORT_NOT_FOUND")  # a report is only found under its own Dependent
    assert_error(download(client, t["pt"], t["dep"], str(uuid.uuid4())), 404, "REPORT_NOT_FOUND")


def test_paging_newest_first(client):
    t = team(client)
    ids = [make(client, t["pt"], t["dep"]).json()["report_id"] for _ in range(3)]
    page = listing(client, t["pt"], t["dep"], limit=2)
    assert page["total"] == 3 and [i["report_id"] for i in page["items"]] == [ids[2], ids[1]]
    assert [i["report_id"] for i in listing(client, t["pt"], t["dep"], limit=2, offset=2)["items"]] == [ids[0]]


def test_delete_removes_the_row_and_the_file(client, reports_dir):
    t = team(client)
    rep = make(client, t["pt"], t["dep"]).json()
    assert len(files(reports_dir)) == 1
    assert client.delete(f"/dependents/{t['dep']}/reports/{rep['report_id']}", headers=auth(t["pt"])).status_code == 204
    assert files(reports_dir) == [] and listing(client, t["pt"], t["dep"])["total"] == 0
    assert_error(client.delete(f"/dependents/{t['dep']}/reports/{rep['report_id']}", headers=auth(t["pt"])), 404, "REPORT_NOT_FOUND")


def test_the_number_of_reports_is_capped(client, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "REPORTS_MAX_PER_PAIR", 2)
    assert make(client, t["pt"], t["dep"]).status_code == 201
    assert make(client, t["pt"], t["dep"]).status_code == 201
    assert_error(make(client, t["pt"], t["dep"]), 409, "REPORT_LIMIT")


def test_a_lost_file_and_a_damaged_file_are_reported_honestly(client, db, reports_dir):
    t = team(client)
    rep = make(client, t["pt"], t["dep"]).json()
    f = files(reports_dir)[0]
    f.write_bytes(b"garbage")
    assert_error(download(client, t["pt"], t["dep"], rep["report_id"]), 500, "FILE_UNREADABLE")
    f.unlink()
    assert_error(download(client, t["pt"], t["dep"], rep["report_id"]), 404, "FILE_NOT_FOUND")


# ------------------------------------------------------------ schedule

def test_schedule_on_change_and_off(client):
    t = team(client)
    dep = t["dep"]
    r = client.get(f"/dependents/{dep}/reports/schedule", headers=auth(t["pt"])).json()
    assert r == {"dependent_id": dep, "frequency": None, "since": None}
    on = put_schedule(client, t["pt"], dep, "weekly")
    assert on.status_code == 200 and on.json()["frequency"] == "weekly" and on.json()["since"]
    again = put_schedule(client, t["pt"], dep, "weekly").json()
    assert again["since"] == on.json()["since"]  # same choice: nothing changes
    month = put_schedule(client, t["pt"], dep, "monthly").json()
    assert month["frequency"] == "monthly" and month["since"] >= on.json()["since"]
    assert_error(put_schedule(client, t["pt"], dep, "daily"), 422, "VALIDATION_ERROR")
    assert client.delete(f"/dependents/{dep}/reports/schedule", headers=auth(t["pt"])).status_code == 204
    assert client.delete(f"/dependents/{dep}/reports/schedule", headers=auth(t["pt"])).status_code == 204  # switching off twice is fine
    assert client.get(f"/dependents/{dep}/reports/schedule", headers=auth(t["pt"])).json()["frequency"] is None


def test_each_guardian_has_their_own_schedule(client, db):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], True).status_code == 200
    put_schedule(client, t["pt"], t["dep"], "weekly")
    put_schedule(client, t["st"], t["dep"], "monthly")
    assert client.get(f"/dependents/{t['dep']}/reports/schedule", headers=auth(t["pt"])).json()["frequency"] == "weekly"
    assert client.get(f"/dependents/{t['dep']}/reports/schedule", headers=auth(t["st"])).json()["frequency"] == "monthly"
    assert db.scalar(select(func.count()).select_from(ReportSchedule)) == 2


# ------------------------------------------------------------ the background job

def test_the_job_makes_last_weeks_report_once_and_tells_the_guardian(client, db):
    t = team(client)
    first, last = data_in_last_week(client, db, t)
    put_schedule(client, t["pt"], t["dep"], "weekly")
    old_schedule(db, primary_id(client, t), t["dep"])
    assert report_service.sweep(db) == 1
    items = listing(client, t["pt"], t["dep"])["items"]
    assert len(items) == 1
    rep = items[0]
    assert (rep["period"], rep["source"], rep["period_start"], rep["period_end"]) == ("weekly", "scheduled", str(first), str(last))
    body = text_of(download(client, t["pt"], t["dep"], rep["report_id"]))
    assert "Weekly health summary" in body and "Metformin" in body and "Oxygen saturation" in body
    note = [n for n in inbox(client, t["pt"])["items"] if n["type"] == "summary_report"]
    assert len(note) == 1 and note[0]["priority"] == "standard" and note[0]["data"]["report_id"] == rep["report_id"]
    assert report_service.sweep(db) == 0  # the same period is not made twice
    assert listing(client, t["pt"], t["dep"])["total"] == 1
    assert len([n for n in inbox(client, t["pt"])["items"] if n["type"] == "summary_report"]) == 1


def test_the_next_week_and_the_month_are_made_when_they_end(client, db):
    t = team(client)
    put_schedule(client, t["pt"], t["dep"], "weekly")
    old_schedule(db, primary_id(client, t), t["dep"], days=100)
    assert report_service.sweep(db) == 1
    soon = datetime.now(timezone.utc) + timedelta(days=7)
    assert report_service.sweep(db, now=soon) == 1  # a week later: the next finished week
    assert report_service.sweep(db, now=soon) == 0
    weeks = [i["period_start"] for i in listing(client, t["pt"], t["dep"])["items"]]
    assert len(set(weeks)) == 2
    put_schedule(client, t["pt"], t["dep"], "monthly")
    old_schedule(db, primary_id(client, t), t["dep"], days=100)
    assert report_service.sweep(db) == 1
    month = [i for i in listing(client, t["pt"], t["dep"])["items"] if i["period"] == "monthly"][0]
    assert (month["period_start"], month["period_end"]) == tuple(str(d) for d in report_service.last_month(local_today()))


def test_a_period_that_ended_before_the_schedule_was_switched_on_is_not_made(client, db):
    t = team(client)
    put_schedule(client, t["pt"], t["dep"], "weekly")  # switched on just now
    assert report_service.sweep(db) == 0
    assert listing(client, t["pt"], t["dep"])["total"] == 0
    # but the week that ends after it was switched on is made
    assert report_service.sweep(db, now=datetime.now(timezone.utc) + timedelta(days=8)) == 1


def test_the_job_skips_guardians_without_permission_or_link(client, db):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], True).status_code == 200
    put_schedule(client, t["st"], t["dep"], "weekly")
    old_schedule(db, uuid.UUID(t["sid"]), t["dep"])
    # only vitals are allowed: the report has only that section
    assert report_service.sweep(db) == 1
    rep = listing(client, t["st"], t["dep"])["items"][0]
    assert rep["includes_vitals"] and not rep["includes_adherence"]
    # permission gone: nothing new is made, nothing breaks
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], False).status_code == 200
    assert report_service.sweep(db, now=datetime.now(timezone.utc) + timedelta(days=7)) == 0
    # a closed Guardian account gets nothing either
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], True).status_code == 200
    db.execute(text("UPDATE users SET closed_at = now() WHERE user_id = :u"), {"u": t["sid"]})
    db.commit()
    assert report_service.sweep(db, now=datetime.now(timezone.utc) + timedelta(days=7)) == 0


def test_a_closed_dependent_gets_no_new_reports(client, db):
    t = team(client)
    put_schedule(client, t["pt"], t["dep"], "weekly")
    old_schedule(db, primary_id(client, t), t["dep"])
    assert close_dep(client, t).status_code == 200
    assert report_service.sweep(db) == 0


def test_a_second_process_making_the_same_report_is_harmless(client, db, reports_dir):
    t = team(client)
    put_schedule(client, t["pt"], t["dep"], "weekly")
    old_schedule(db, primary_id(client, t), t["dep"])
    s = db.scalar(select(ReportSchedule))
    first, last = report_service.last_week(local_today())
    report_service._make(db, s.guardian_id, s.dependent_id, first, last, "weekly", "scheduled", True, True)  # "the other process"
    assert len(files(reports_dir)) == 1
    assert report_service._scheduled_one(db, s, first, last) == 0  # the unique index refuses the duplicate
    assert len(files(reports_dir)) == 1 and db.scalar(select(func.count()).select_from(SummaryReport)) == 1  # and its file was removed again


def test_old_reports_are_removed_by_the_job(client, db, reports_dir):
    t = team(client)
    make(client, t["pt"], t["dep"])
    make(client, t["pt"], t["dep"])
    db.execute(text("UPDATE summary_reports SET created_at = now() - interval '200 days' WHERE report_id = (SELECT report_id FROM summary_reports ORDER BY created_at LIMIT 1)"))
    db.commit()
    report_service.sweep(db)
    assert listing(client, t["pt"], t["dep"])["total"] == 1 and len(files(reports_dir)) == 1


# ------------------------------------------------------------ the numbers come from 7.1, for any finished period

def test_analytics_can_look_at_a_finished_period(client, db):
    t = team(client)
    s = sched(client, t)
    day = local_today() - timedelta(days=10)
    dose(db, s, ms.occurrence(day, datetime.min.time().replace(hour=8)), "taken")
    dose(db, s, ms.occurrence(local_today() - timedelta(days=1), datetime.min.time().replace(hour=8)), "missed")
    reading(db, t["dep"], "spo2", 96, ms.occurrence(day, datetime.min.time().replace(hour=9)))
    reading(db, t["dep"], "spo2", 80, datetime.now(timezone.utc) - timedelta(hours=2))
    dep = uuid.UUID(t["dep"])
    a = analytics_service._adherence(db, dep, 7, day + timedelta(days=3))  # the 7 days that end 3 days after the dose
    assert (a.taken, a.missed, a.to_date) == (1, 0, day + timedelta(days=3))
    v = analytics_service._vitals(db, dep, 7, "spo2", day + timedelta(days=3)).metrics[0]
    assert (v.count, v.max) == (1, 96.0)


# ------------------------------------------------------------ retention (FR-O1)

def test_reports_are_deleted_with_the_dependent_and_with_a_closed_guardian(client, db, reports_dir):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    make(client, t["pt"], t["dep"])
    make(client, t["st"], t["dep"])
    put_schedule(client, t["st"], t["dep"], "monthly")
    assert len(files(reports_dir)) == 2
    sid = uuid.UUID(t["sid"])
    assert client.post("/account/close", json={"password": "correct-horse-9"}, headers=auth(t["st"])).status_code == 200
    make_due(db, sid, days_ago=0)
    assert retention_service.sweep(db) == 1
    assert db.scalar(select(func.count()).select_from(SummaryReport).where(SummaryReport.guardian_id == sid)) == 0
    assert db.scalar(select(func.count()).select_from(ReportSchedule)) == 0
    assert len(files(reports_dir)) == 1  # the Primary's is still there
    assert close_dep(client, t).status_code == 200
    make_due(db, uuid.UUID(t["dep"]), days_ago=0)
    assert retention_service.sweep(db) == 1
    assert db.scalar(select(func.count()).select_from(SummaryReport)) == 0 and files(reports_dir) == []
