"""
Task 5.3 tests: manual vitals entry (FR-H1): blood pressure, blood sugar, SpO2, temperature.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import AuditLog, VitalReading
from tests.conftest import TEST_DATABASE_URL  # noqa: F401
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_records import add, allow, export, ok, pdf_text, share, store, PDF  # noqa: F401 (store is an autouse fixture)


def vadd(client, token, dep, **body):
    body.setdefault("metric_type", "blood_pressure")
    if body["metric_type"] == "blood_pressure":
        body.setdefault("value", 120)
        body.setdefault("diastolic", 80)
    else:
        body.setdefault("value", {"blood_sugar": 100, "spo2": 97, "temperature": 36.8}.get(body["metric_type"], 72))
    return client.post(f"/dependents/{dep}/vitals", json=body, headers=auth(token))


def vlist(client, token, dep, **params):
    r = client.get(f"/dependents/{dep}/vitals", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def now_iso(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def count(db, dep):
    return db.scalar(select(func.count()).select_from(VitalReading).where(VitalReading.dependent_id == uuid.UUID(dep)))


def audits(db, action):
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))


# ------------------------------------------------------------ who may do what

def test_dependent_and_primary_can_add_and_see(client, store):
    t = team(client)
    a = ok(vadd(client, t["dt"], t["dep"]))
    assert a["value"] == 120 and a["diastolic"] == 80 and a["unit"] == "mmHg" and a["source"] == "manual"
    assert a["can_delete"] is True and a["already_saved"] is False
    b = ok(vadd(client, t["pt"], t["dep"], metric_type="spo2", value=96))
    assert b["recorded_by"] != a["recorded_by"]
    assert vlist(client, t["dt"], t["dep"])["total"] == 2
    assert vlist(client, t["pt"], t["dep"])["total"] == 2


def test_secondary_needs_the_health_records_permission(client, store):
    t = team(client)
    assert_error(vadd(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert client.get(f"/dependents/{t['dep']}/vitals", headers=auth(t["st"])).status_code == 403
    assert client.get(f"/dependents/{t['dep']}/vitals/latest", headers=auth(t["st"])).status_code == 403
    allow(client, t)
    ok(vadd(client, t["st"], t["dep"]))
    assert vlist(client, t["st"], t["dep"])["total"] == 1
    allow(client, t, False)
    assert client.get(f"/dependents/{t['dep']}/vitals", headers=auth(t["st"])).status_code == 403


def test_strangers_and_anonymous_are_refused(client, store):
    from tests.test_records import stranger_dependent_token
    t = team(client)
    other, _ = stranger_dependent_token(client, 5)
    assert vadd(client, other, t["dep"]).status_code == 403
    assert client.get(f"/dependents/{t['dep']}/vitals", headers=auth(other)).status_code == 403
    assert client.post(f"/dependents/{t['dep']}/vitals", json={"metric_type": "spo2", "value": 97}).status_code == 401
    assert client.get(f"/dependents/{t['dep']}/vitals").status_code == 401
    assert client.get(f"/dependents/{t['dep']}/vitals/export").status_code == 401


# ------------------------------------------------------------ validation and units

def test_ranges_are_enforced(client, store):
    t = team(client)
    bad = [
        dict(metric_type="blood_pressure", value=49, diastolic=40),
        dict(metric_type="blood_pressure", value=301, diastolic=80),
        dict(metric_type="blood_pressure", value=120, diastolic=29),
        dict(metric_type="blood_pressure", value=120, diastolic=201),
        dict(metric_type="blood_pressure", value=80, diastolic=80),
        dict(metric_type="blood_sugar", value=9),
        dict(metric_type="blood_sugar", value=1001),
        dict(metric_type="spo2", value=49),
        dict(metric_type="spo2", value=101),
        dict(metric_type="temperature", value=29.9),
        dict(metric_type="temperature", value=45.1),
    ]
    for b in bad:
        assert_error(vadd(client, t["dt"], t["dep"], **b), 422, "VITAL_OUT_OF_RANGE")
    good = [
        dict(metric_type="blood_pressure", value=50, diastolic=30),
        dict(metric_type="blood_pressure", value=300, diastolic=200),
        dict(metric_type="blood_sugar", value=10), dict(metric_type="blood_sugar", value=1000),
        dict(metric_type="spo2", value=50), dict(metric_type="spo2", value=100),
        dict(metric_type="temperature", value=30), dict(metric_type="temperature", value=45),
    ]
    for g in good:
        ok(vadd(client, t["dt"], t["dep"], **g))
    assert vlist(client, t["dt"], t["dep"])["total"] == len(good)


def test_shape_errors(client, store):
    t = team(client)
    tok, dep = t["dt"], t["dep"]
    assert_error(vadd(client, tok, dep, metric_type="blood_pressure", value=120, diastolic=None), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", value=97, diastolic=80), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", value=97, context="fasting"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="heart_rate", value=72), 422, "VALIDATION_ERROR")  # band only (Task 5.4)
    assert_error(vadd(client, tok, dep, metric_type="weight", value=70), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", value="abc"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="blood_sugar", value=100, context="midnight"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="blood_pressure", unit="kPa"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", unit="mg"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="temperature", unit="K"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="blood_sugar", unit="g"), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", note="x" * 201), 422, "VALIDATION_ERROR")
    assert_error(vadd(client, tok, dep, metric_type="spo2", note="bad\x00note"), 422, "VALIDATION_ERROR")
    assert count_rows(client, t) == 0


def count_rows(client, t):
    return vlist(client, t["pt"], t["dep"])["total"]


def test_unit_conversion(client, store):
    t = team(client)
    s = ok(vadd(client, t["dt"], t["dep"], metric_type="blood_sugar", value=5.5, unit="mmol/L"))
    assert s["unit"] == "mg/dL" and abs(s["value"] - 99.1) < 0.05
    f = ok(vadd(client, t["dt"], t["dep"], metric_type="temperature", value=98.6, unit="F"))
    assert f["unit"] == "C" and abs(f["value"] - 37.0) < 0.05
    assert_error(vadd(client, t["dt"], t["dep"], metric_type="temperature", value=120, unit="F"), 422, "VITAL_OUT_OF_RANGE")
    assert_error(vadd(client, t["dt"], t["dep"], metric_type="blood_sugar", value=0.1, unit="mmol/L"), 422, "VITAL_OUT_OF_RANGE")
    c = ok(vadd(client, t["dt"], t["dep"], metric_type="blood_sugar", value=100, context="fasting", note="before breakfast"))
    assert c["context"] == "fasting" and c["note"] == "before breakfast"


# ------------------------------------------------------------ time

def test_recorded_at_rules(client, store):
    t = team(client)
    tok, dep = t["dt"], t["dep"]
    r = ok(vadd(client, tok, dep, recorded_at=now_iso(hours=3)))
    assert r["recorded_at"] < r["created_at"]
    assert_error(vadd(client, tok, dep, recorded_at="2026-10-01T09:00:00"), 422, "VALIDATION_ERROR")  # no zone
    assert_error(vadd(client, tok, dep, recorded_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()), 422, "INVALID_DATE")
    assert_error(vadd(client, tok, dep, recorded_at=now_iso(days=366)), 422, "INVALID_DATE")
    ok(vadd(client, tok, dep, recorded_at=now_iso(days=364)))


# ------------------------------------------------------------ retries

def test_client_id_makes_a_retry_safe(client, store, db):
    t = team(client)
    cid = str(uuid.uuid4())
    a = ok(vadd(client, t["dt"], t["dep"], client_id=cid, recorded_at=now_iso(minutes=5)))
    b = ok(vadd(client, t["dt"], t["dep"], client_id=cid, recorded_at=a["recorded_at"]), 200)
    assert b["reading_id"] == a["reading_id"] and b["already_saved"] is True
    c = ok(vadd(client, t["dt"], t["dep"], client_id=cid), 200)  # no recorded_at sent: still the same reading
    assert c["reading_id"] == a["reading_id"]
    assert_error(vadd(client, t["dt"], t["dep"], client_id=cid, value=130), 409, "CLIENT_ID_REUSED")
    assert count(db, t["dep"]) == 1 and audits(db, "vital_added") == 1
    # another person may use the same client_id
    ok(vadd(client, t["pt"], t["dep"], client_id=cid))
    assert count(db, t["dep"]) == 2


def test_parallel_retries_save_once(client, store, db):
    t = team(client)
    cid = str(uuid.uuid4())
    at = now_iso(minutes=2)
    bar = Barrier(6)

    def go(_):
        bar.wait()
        return vadd(client, t["dt"], t["dep"], client_id=cid, recorded_at=at).status_code

    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(go, range(6)))
    assert sorted(set(codes)) in ([200, 201], [201]) and codes.count(201) == 1, codes
    assert count(db, t["dep"]) == 1


def test_cap_per_dependent(client, store, db, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "VITALS_MAX_PER_DEPENDENT", 3, raising=False)
    for _ in range(3):
        ok(vadd(client, t["dt"], t["dep"]))
    assert_error(vadd(client, t["dt"], t["dep"]), 409, "VITALS_LIMIT")
    first = vlist(client, t["dt"], t["dep"])["items"][0]["reading_id"]
    assert client.delete(f"/dependents/{t['dep']}/vitals/{first}", headers=auth(t["dt"])).status_code == 204
    ok(vadd(client, t["dt"], t["dep"]))


def test_cap_cannot_be_beaten_in_parallel(client, store, db, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "VITALS_MAX_PER_DEPENDENT", 2, raising=False)
    bar = Barrier(6)

    def go(_):
        bar.wait()
        return vadd(client, t["dt"], t["dep"]).status_code

    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(go, range(6)))
    assert codes.count(201) == 2 and codes.count(409) == 4, codes
    assert count(db, t["dep"]) == 2


# ------------------------------------------------------------ list, latest, one, delete

def test_list_filters_paging_and_order(client, store):
    t = team(client)
    tok, dep = t["dt"], t["dep"]
    ok(vadd(client, tok, dep, metric_type="spo2", value=95, recorded_at=now_iso(hours=5)))
    ok(vadd(client, tok, dep, metric_type="spo2", value=98, recorded_at=now_iso(hours=1)))
    ok(vadd(client, tok, dep, metric_type="temperature", value=37.1, recorded_at=now_iso(hours=3)))
    ok(vadd(client, tok, dep))
    allv = vlist(client, tok, dep)
    assert allv["total"] == 4
    times = [i["recorded_at"] for i in allv["items"]]
    assert times == sorted(times, reverse=True)
    sp = vlist(client, tok, dep, metric_type="spo2")
    assert [i["value"] for i in sp["items"]] == [98, 95]
    assert vlist(client, tok, dep, limit=1, offset=1)["items"][0]["metric_type"] != "x" and len(vlist(client, tok, dep, limit=1, offset=1)["items"]) == 1
    since = vlist(client, tok, dep, **{"from": now_iso(hours=4)})
    assert since["total"] == 3
    until = vlist(client, tok, dep, to=now_iso(hours=4))
    assert until["total"] == 1 and until["items"][0]["value"] == 95
    r = client.get(f"/dependents/{dep}/vitals", params={"metric_type": "weight"}, headers=auth(tok))
    assert_error(r, 422, "VALIDATION_ERROR")
    r = client.get(f"/dependents/{dep}/vitals", params={"from": "2026-10-01T00:00:00"}, headers=auth(tok))
    assert_error(r, 422, "VALIDATION_ERROR")
    r = client.get(f"/dependents/{dep}/vitals", params={"from": now_iso(hours=1), "to": now_iso(hours=2)}, headers=auth(tok))
    assert_error(r, 422, "VALIDATION_ERROR")
    assert client.get(f"/dependents/{dep}/vitals", params={"limit": 0}, headers=auth(tok)).status_code == 422
    assert client.get(f"/dependents/{dep}/vitals", params={"limit": 201}, headers=auth(tok)).status_code == 422


def test_latest_shows_newest_per_metric(client, store):
    t = team(client)
    tok, dep = t["dt"], t["dep"]
    empty = client.get(f"/dependents/{dep}/vitals/latest", headers=auth(tok)).json()
    assert set(empty["latest"]) == {"blood_pressure", "blood_sugar", "spo2", "temperature", "heart_rate"}
    assert all(v is None for v in empty["latest"].values())
    ok(vadd(client, tok, dep, metric_type="spo2", value=90, recorded_at=now_iso(hours=2)))
    ok(vadd(client, tok, dep, metric_type="spo2", value=97, recorded_at=now_iso(hours=1)))
    ok(vadd(client, tok, dep, metric_type="spo2", value=88, recorded_at=now_iso(hours=9)))  # older, entered last
    got = client.get(f"/dependents/{dep}/vitals/latest", headers=auth(tok)).json()["latest"]
    assert got["spo2"]["value"] == 97 and got["blood_pressure"] is None and got["heart_rate"] is None


def test_get_and_delete_rules(client, store, db):
    t = team(client)
    allow(client, t)
    mine_ = ok(vadd(client, t["st"], t["dep"]))
    prim = ok(vadd(client, t["pt"], t["dep"]))
    dep_ = ok(vadd(client, t["dt"], t["dep"]))
    path = lambda r: f"/dependents/{t['dep']}/vitals/{r['reading_id']}"
    assert client.get(path(prim), headers=auth(t["st"])).json()["can_delete"] is False
    assert client.get(path(mine_), headers=auth(t["st"])).json()["can_delete"] is True
    assert_error(client.delete(path(prim), headers=auth(t["st"])), 403, "VITAL_MODIFY_DENIED")
    assert_error(client.delete(path(dep_), headers=auth(t["st"])), 403, "VITAL_MODIFY_DENIED")
    assert_error(client.delete(path(mine_), headers=auth(t["dt"])), 403, "VITAL_MODIFY_DENIED")  # a Dependent cannot delete a Guardian's entry
    assert client.delete(path(mine_), headers=auth(t["pt"])).status_code == 204  # the Primary can
    assert client.delete(path(dep_), headers=auth(t["dt"])).status_code == 204
    assert_error(client.get(path(dep_), headers=auth(t["pt"])), 404, "VITAL_NOT_FOUND")
    assert_error(client.delete(path(dep_), headers=auth(t["pt"])), 404, "VITAL_NOT_FOUND")
    assert audits(db, "vital_deleted") == 2
    # a reading id of another Dependent is not found under this one
    assert_error(client.get(f"/dependents/{t['dep']}/vitals/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "VITAL_NOT_FOUND")


def test_no_medical_judgement_in_the_response(client, store):
    t = team(client)
    r = ok(vadd(client, t["dt"], t["dep"], value=190, diastolic=120))
    assert not ({"status", "level", "severity", "warning", "alert", "is_abnormal"} & set(r))


# ------------------------------------------------------------ export

def test_separate_vitals_pdf(client, store, db):
    t = team(client)
    ok(vadd(client, t["dt"], t["dep"], value=128, diastolic=82))
    ok(vadd(client, t["dt"], t["dep"], metric_type="blood_sugar", value=112, context="fasting"))
    ok(vadd(client, t["dt"], t["dep"], metric_type="temperature", value=36.8))
    ok(vadd(client, t["pt"], t["dep"], metric_type="spo2", value=97, note="after walk"))
    r = client.get(f"/dependents/{t['dep']}/vitals/export", headers=auth(t["pt"]))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "no-store" in r.headers["cache-control"] and "vitals" in r.headers["content-disposition"]
    text, _ = pdf_text(r.content)
    for s in ("128/82 mmHg", "112 mg/dL (fasting)", "97 %", "after walk"):
        assert s in text, text
    assert "36.8" in text and "u00b0" not in text
    assert audits(db, "vitals_exported") == 1


def test_export_period_and_permission(client, store):
    t = team(client)
    ok(vadd(client, t["dt"], t["dep"], recorded_at=now_iso(days=1)))
    assert client.get(f"/dependents/{t['dep']}/vitals/export", headers=auth(t["st"])).status_code == 403
    y = datetime.now(timezone.utc).year
    assert client.get(f"/dependents/{t['dep']}/vitals/export", params={"scope": "year", "year": y}, headers=auth(t["dt"])).status_code == 200
    assert client.get(f"/dependents/{t['dep']}/vitals/export", params={"scope": "year"}, headers=auth(t["dt"])).status_code == 422
    assert client.get(f"/dependents/{t['dep']}/vitals/export", params={"scope": "month", "year": y, "month": 13}, headers=auth(t["dt"])).status_code == 422
    r = client.get(f"/dependents/{t['dep']}/vitals/export", params={"scope": "year", "year": 2001}, headers=auth(t["dt"]))
    text, _ = pdf_text(r.content)
    assert "120/80" not in text  # nothing in 2001


def test_records_export_can_include_vitals(client, store):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Blood test", file=PDF))
    ok(vadd(client, t["dt"], t["dep"], value=131, diastolic=84))
    plain, _ = pdf_text(export(client, t["pt"], t["dep"]).content)
    with_v, _ = pdf_text(export(client, t["pt"], t["dep"], include_vitals="true").content)
    assert "131/84" not in plain and "131/84" in with_v and "Blood test" in with_v


def test_doctor_link_can_include_vitals(client, store):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Blood test", file=PDF))
    ok(vadd(client, t["dt"], t["dep"], value=133, diastolic=86))
    a = ok(share(client, t["pt"], t["dep"]))
    b = ok(share(client, t["pt"], t["dep"], include_vitals=True))
    assert a["include_vitals"] is False and b["include_vitals"] is True
    ta, _ = pdf_text(client.get(f"/shared/records/{a['token']}").content)
    tb, _ = pdf_text(client.get(f"/shared/records/{b['token']}").content)
    assert "133/86" not in ta and "133/86" in tb
    listed = client.get(f"/dependents/{t['dep']}/records/share", headers=auth(t["pt"])).json()
    assert sorted(i["include_vitals"] for i in listed["items"]) == [False, True]
