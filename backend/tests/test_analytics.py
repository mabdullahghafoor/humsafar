"""
Task 7.1 tests: adherence and vitals analytics for the Guardian (FR-Q1).
"""

import uuid
from datetime import datetime, time, timedelta, timezone

from app.models import MedicationConfirmation, VitalReading
from app.services import medication_service as ms
from tests.test_linkage import assert_error, auth, make_dependent
from tests.test_location import team
from tests.test_medication import add as add_med
from tests.test_permissions import put
from tests.test_records import store  # noqa: F401 (autouse fixture used by the vitals tests)
from tests.test_vitals import vadd

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


def local_today():
    return NOW().astimezone(ms.tz()).date()


def at(days_ago, hh=8, mm=0):
    """The UTC moment of hh:mm local time, `days_ago` local days back."""
    return ms.occurrence(local_today() - timedelta(days=days_ago), time(hh, mm))


def sched(client, t, drug="Metformin", dosage="500 mg", hhmm="08:00"):
    r = add_med(client, t["pt"], t["dep"], drug_name=drug, dosage=dosage, times=[hhmm])
    assert r.status_code == 201, r.text
    return r.json()["items"][0]["schedule_id"]


def dose(db, schedule_id, when, status):
    db.add(MedicationConfirmation(
        schedule_id=uuid.UUID(schedule_id), scheduled_for=when, status=status,
        confirmed_at=when + timedelta(minutes=5) if status == "taken" else None,
    ))
    db.commit()


def reading(db, dep, metric, value, when, source="manual", diastolic=None):
    db.add(VitalReading(
        dependent_id=uuid.UUID(dep), metric_type=metric, value=value, diastolic=diastolic,
        recorded_at=when, source=source,
    ))
    db.commit()


def adh(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/analytics/adherence", params=params, headers=auth(token))


def vit(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/analytics/vitals", params=params, headers=auth(token))


def over(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/analytics", params=params, headers=auth(token))


def metric(body, name):
    return next(m for m in body["metrics"] if m["metric_type"] == name)


# ------------------------------------------------------------ who may read

def test_only_guardians_with_permission_may_read(client, db):
    t = team(client)
    for fn in (adh, vit, over):
        assert fn(client, t["pt"], t["dep"]).status_code == 200
        assert_error(fn(client, t["dt"], t["dep"]), 403, "FORBIDDEN")  # the Dependent is refused
    assert client.get(f"/dependents/{t['dep']}/analytics").status_code == 401
    # a Secondary has no access until the Primary grants it, module by module
    assert_error(adh(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(vit(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(over(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    assert adh(client, t["st"], t["dep"]).status_code == 200
    assert_error(vit(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    body = over(client, t["st"], t["dep"]).json()
    assert body["adherence"] is not None and body["vitals"] is None
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], True).status_code == 200
    assert vit(client, t["st"], t["dep"]).status_code == 200
    body = over(client, t["st"], t["dep"]).json()
    assert body["adherence"] is not None and body["vitals"] is not None
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], False).status_code == 200
    body = over(client, t["st"], t["dep"]).json()
    assert body["adherence"] is None and body["vitals"] is not None


def test_a_guardian_of_someone_else_gets_nothing(client):
    t = team(client)
    other = make_dependent(client, 2)
    for fn in (adh, vit, over):
        assert_error(fn(client, t["pt"], other), 403, "NOT_LINKED_TO_DEPENDENT")


def test_days_must_be_1_to_90_and_metric_must_exist(client):
    t = team(client)
    for bad in (0, 91, -3):
        for fn in (adh, vit, over):
            assert_error(fn(client, t["pt"], t["dep"], days=bad), 422, "VALIDATION_ERROR")
    assert adh(client, t["pt"], t["dep"], days=1).status_code == 200
    assert adh(client, t["pt"], t["dep"], days=90).status_code == 200
    assert_error(vit(client, t["pt"], t["dep"], metric_type="mood"), 422, "VALIDATION_ERROR")


def test_health_data_is_never_cached(client):
    t = team(client)
    for fn in (adh, vit, over):
        assert "no-store" in fn(client, t["pt"], t["dep"]).headers["cache-control"]


# ------------------------------------------------------------ adherence

def test_empty_history_is_a_clean_answer(client):
    t = team(client)
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert (a["taken"], a["missed"], a["waiting"], a["rate_percent"]) == (0, 0, 0, None)
    assert a["change"] == "not_enough_data" and a["change_points"] is None and a["perfect_days_in_a_row"] == 0
    assert len(a["daily"]) == 7 and a["by_medicine"] == []
    assert a["daily"][-1]["date"] == str(local_today()) and a["to_date"] == str(local_today())
    assert a["timezone"] == "Asia/Karachi"
    v = vit(client, t["pt"], t["dep"]).json()
    assert [m["metric_type"] for m in v["metrics"]] == ["blood_pressure", "blood_sugar", "spo2", "temperature", "heart_rate"]
    assert all(m["count"] == 0 and m["avg"] is None and m["latest"] is None and m["trend"] == "not_enough_data" and m["daily"] == [] for m in v["metrics"])


def test_adherence_counts_rate_days_and_medicines(client, db):
    t = team(client)
    a_id = sched(client, t, "Metformin", "500 mg", "08:00")
    b_id = sched(client, t, "Aspirin", "75 mg", "20:00")
    # today 1 taken; yesterday 1 taken + 1 missed; 2 days ago 1 taken + 1 missed
    dose(db, a_id, at(0, 0, 1), "taken")
    dose(db, a_id, at(1), "taken")
    dose(db, b_id, at(1, 20), "missed")
    dose(db, a_id, at(2), "taken")
    dose(db, b_id, at(2, 20), "missed")
    dose(db, a_id, at(3), "taken")  # a perfect day older than the missed ones must not extend the streak
    r = adh(client, t["pt"], t["dep"], days=7)
    assert r.status_code == 200, r.text
    a = r.json()
    assert (a["taken"], a["missed"], a["waiting"]) == (4, 2, 0)
    assert a["rate_percent"] == 66.7
    by_day = {d["date"]: d for d in a["daily"]}
    assert len(a["daily"]) == 7 and a["daily"][0]["date"] == str(local_today() - timedelta(days=6))
    assert (by_day[str(local_today())]["taken"], by_day[str(local_today())]["rate_percent"]) == (1, 100.0)
    y = by_day[str(local_today() - timedelta(days=1))]
    assert (y["taken"], y["missed"], y["rate_percent"]) == (1, 1, 50.0)
    meds = {m["drug_name"]: m for m in a["by_medicine"]}
    assert (meds["Metformin"]["taken"], meds["Metformin"]["missed"], meds["Metformin"]["rate_percent"]) == (4, 0, 100.0)
    assert (meds["Aspirin"]["taken"], meds["Aspirin"]["missed"], meds["Aspirin"]["rate_percent"]) == (0, 2, 0.0)
    assert meds["Aspirin"]["dosage"] == "75 mg"
    assert a["perfect_days_in_a_row"] == 1  # only today; yesterday had a missed dose
    # a shorter look-back only sees its own days
    assert adh(client, t["pt"], t["dep"], days=1).json()["taken"] == 1


def test_waiting_doses_are_not_in_the_rate_and_future_doses_do_not_exist_yet(client, db):
    t = team(client)
    s = sched(client, t)
    dose(db, s, NOW() - timedelta(minutes=30), "pending")
    dose(db, s, NOW() + timedelta(hours=3), "pending")  # not due yet
    dose(db, s, at(1), "taken")
    a = adh(client, t["pt"], t["dep"], days=3).json()
    assert (a["taken"], a["missed"], a["waiting"], a["rate_percent"]) == (1, 0, 1, 100.0)


def test_change_against_the_period_before(client, db):
    t = team(client)
    s = sched(client, t)
    # previous 7 days (8..14 days ago): 1 taken, 3 missed = 25 %.  This week: 3 taken, 1 missed = 75 %.
    dose(db, s, at(9), "taken")
    for d in (10, 11, 12):
        dose(db, s, at(d), "missed")
    for d in (1, 2, 3):
        dose(db, s, at(d), "taken")
    dose(db, s, at(4), "missed")
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert a["rate_percent"] == 75.0 and a["previous"] == {"taken": 1, "missed": 3, "rate_percent": 25.0}
    assert a["change_points"] == 50.0 and a["change"] == "improving"
    # the other way round
    b = adh(client, t["pt"], t["dep"], days=14)  # 14 days: 4 taken 4 missed = 50 %; before that: nothing
    assert b.json()["previous"]["rate_percent"] is None and b.json()["change"] == "not_enough_data"


def test_declining_and_steady(client, db):
    t = team(client)
    s = sched(client, t)
    dose(db, s, at(1), "missed")
    dose(db, s, at(2), "taken")  # this week 50 %
    for d in (8, 9, 10):
        dose(db, s, at(d), "taken")  # previous week 100 %
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert a["change"] == "declining" and a["change_points"] == -50.0
    dose(db, s, at(11), "missed")
    dose(db, s, at(12), "missed")
    dose(db, s, at(13), "taken")  # previous week now 4 taken 2 missed = 66.7 %
    dose(db, s, at(3), "taken")
    dose(db, s, at(4), "taken")  # this week 4 taken 1 missed = 80 %
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert a["change"] == "improving"  # 80 vs 66.7 = +13.3


def test_steady_when_the_change_is_small(client, db):
    t = team(client)
    s = sched(client, t)
    for d in (1, 2, 3):
        dose(db, s, at(d), "taken")
    dose(db, s, at(4), "missed")  # 75 %
    for d in (8, 9, 10):
        dose(db, s, at(d), "taken")
    dose(db, s, at(11), "missed")  # 75 %
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert a["change_points"] == 0.0 and a["change"] == "steady"


def test_a_removed_schedule_keeps_its_history(client, db):
    t = team(client)
    s = sched(client, t)
    dose(db, s, at(1), "taken")
    dose(db, s, at(2), "missed")
    assert client.delete(f"/dependents/{t['dep']}/medications/{s}", headers=auth(t["pt"])).status_code == 204
    a = adh(client, t["pt"], t["dep"], days=7).json()
    assert (a["taken"], a["missed"]) == (1, 1) and a["by_medicine"][0]["drug_name"] == "Metformin"


def test_a_dose_is_counted_on_its_local_day(client, db):
    t = team(client)
    s = sched(client, t)
    # 23:30 in Karachi is 18:30 UTC: still the same local day; 00:30 in Karachi is 19:30 UTC the day before.
    dose(db, s, at(2, 23, 30), "taken")
    dose(db, s, at(1, 0, 30), "missed")
    by_day = {d["date"]: d for d in adh(client, t["pt"], t["dep"], days=4).json()["daily"]}
    assert by_day[str(local_today() - timedelta(days=2))]["taken"] == 1
    assert by_day[str(local_today() - timedelta(days=1))]["missed"] == 1


def test_another_dependents_doses_are_never_counted(client, db):
    t = team(client)
    s = sched(client, t)
    dose(db, s, at(1), "taken")
    other = make_dependent(client, 2)
    assert adh(client, t["pt"], t["dep"]).json()["taken"] == 1
    assert other != t["dep"]


# ------------------------------------------------------------ vitals

def test_vitals_summary_per_metric(client, db):
    t = team(client)
    for i, (sy, di) in enumerate([(120, 80), (130, 90), (140, 100)]):
        assert vadd(client, t["pt"], t["dep"], metric_type="blood_pressure", value=sy, diastolic=di,
                    recorded_at=(NOW() - timedelta(days=2 - i, hours=1)).isoformat()).status_code == 201
    assert vadd(client, t["pt"], t["dep"], metric_type="blood_sugar", value=100, recorded_at=(NOW() - timedelta(hours=2)).isoformat()).status_code == 201
    v = vit(client, t["pt"], t["dep"], days=7).json()
    bp = metric(v, "blood_pressure")
    assert (bp["count"], bp["manual_count"], bp["wearable_count"], bp["unit"]) == (3, 3, 0, "mmHg")
    assert (bp["avg"], bp["min"], bp["max"]) == (130.0, 120.0, 140.0)
    assert (bp["avg_diastolic"], bp["min_diastolic"], bp["max_diastolic"]) == (90.0, 80.0, 100.0)
    assert bp["latest"]["value"] == 140.0 and bp["latest"]["diastolic"] == 100.0 and bp["latest"]["source"] == "manual"
    assert len(bp["daily"]) == 3 and bp["daily"] == sorted(bp["daily"], key=lambda d: d["date"])
    sugar = metric(v, "blood_sugar")
    assert sugar["count"] == 1 and sugar["avg_diastolic"] is None and sugar["unit"] == "mg/dL"
    assert metric(v, "spo2")["count"] == 0
    only = vit(client, t["pt"], t["dep"], days=7, metric_type="blood_sugar").json()
    assert [m["metric_type"] for m in only["metrics"]] == ["blood_sugar"]


def test_vitals_trend_describes_numbers_only(client, db):
    t = team(client)
    dep = t["dep"]
    # 30 days: first half = days 29..15 ago, second half = days 14..0 ago
    reading(db, dep, "spo2", 94, NOW() - timedelta(days=25))
    reading(db, dep, "spo2", 98, NOW() - timedelta(days=3))
    reading(db, dep, "temperature", 37.0, NOW() - timedelta(days=22))
    reading(db, dep, "temperature", 36.0, NOW() - timedelta(days=2))
    reading(db, dep, "blood_sugar", 100, NOW() - timedelta(days=20))
    reading(db, dep, "blood_sugar", 101, NOW() - timedelta(days=1))
    reading(db, dep, "heart_rate", 70, NOW() - timedelta(days=1), source="wearable")  # nothing in the first half
    v = vit(client, t["pt"], dep, days=30).json()
    spo2, temp, sugar, hr = (metric(v, n) for n in ("spo2", "temperature", "blood_sugar", "heart_rate"))
    assert (spo2["trend"], spo2["change_percent"]) == ("rising", 4.3)
    assert temp["trend"] == "steady" and temp["change_percent"] == -2.7  # under 3 % is steady
    assert (sugar["trend"], sugar["change_percent"]) == ("steady", 1.0)
    assert (hr["trend"], hr["change_percent"]) == ("not_enough_data", None)
    assert "good" not in str(v).lower() and "bad" not in str(v).lower()


def test_falling_trend(client, db):
    t = team(client)
    reading(db, t["dep"], "blood_sugar", 200, NOW() - timedelta(days=20))
    reading(db, t["dep"], "blood_sugar", 150, NOW() - timedelta(days=2))
    m = metric(vit(client, t["pt"], t["dep"], days=30).json(), "blood_sugar")
    assert (m["trend"], m["change_percent"]) == ("falling", -25.0)


def test_band_readings_are_counted_and_marked(client, db):
    t = team(client)
    for i in range(4):
        reading(db, t["dep"], "heart_rate", 70 + i, NOW() - timedelta(hours=i + 1), source="wearable")
    reading(db, t["dep"], "spo2", 96, NOW() - timedelta(hours=1), source="wearable")
    assert vadd(client, t["pt"], t["dep"], metric_type="spo2", value=98).status_code == 201
    v = vit(client, t["pt"], t["dep"], days=3).json()  # 3 days, so the hours-ago readings stay inside even just after midnight
    hr = metric(v, "heart_rate")
    assert (hr["count"], hr["wearable_count"], hr["manual_count"], hr["avg"]) == (4, 4, 0, 71.5)
    assert hr["latest"]["value"] == 70.0 and hr["latest"]["source"] == "wearable"
    spo2 = metric(v, "spo2")
    assert (spo2["count"], spo2["wearable_count"], spo2["manual_count"]) == (2, 1, 1)


def test_readings_outside_the_window_and_of_others_are_left_out(client, db):
    t = team(client)
    reading(db, t["dep"], "spo2", 90, NOW() - timedelta(days=40))
    reading(db, t["dep"], "spo2", 97, NOW() - timedelta(days=1))
    other = make_dependent(client, 2)
    reading(db, other, "spo2", 50, NOW() - timedelta(days=1))
    m = metric(vit(client, t["pt"], t["dep"], days=30).json(), "spo2")
    assert (m["count"], m["min"], m["max"]) == (1, 97.0, 97.0)
    m = metric(vit(client, t["pt"], t["dep"], days=90).json(), "spo2")
    assert (m["count"], m["min"]) == (2, 90.0)


def test_overview_has_both_parts(client, db):
    t = team(client)
    s = sched(client, t)
    dose(db, s, at(1), "taken")
    reading(db, t["dep"], "spo2", 97, NOW() - timedelta(days=1))
    body = over(client, t["pt"], t["dep"], days=7).json()
    assert body["dependent_id"] == t["dep"] and body["days"] == 7
    assert body["adherence"]["taken"] == 1 and metric(body["vitals"], "spo2")["count"] == 1
