"""
Task 5.4 tests: wearable band with mock data (FR-H2): pair, sync, status, "no data" detection, exports.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import AuditLog, EscalationEvent, Notification, VitalReading, WearableDevice
from app.services import notification_service, wearable_service
from app.services.device_health_service import OFFLINE
from tests.test_linkage import assert_error, auth
from tests.test_location import send, team, utcnow
from tests.test_records import allow, export, ok, pdf_text, store  # noqa: F401 (store is an autouse fixture)
from tests.test_vitals import vadd, vlist

ADDR = "C4:5B:BE:12:34:56"
S = get_settings()


def pair(client, token, dep, **body):
    body.setdefault("ble_address", ADDR)
    return client.post(f"/dependents/{dep}/wearable", json=body, headers=auth(token))


def sync(client, token, dep, readings):
    return client.post(f"/dependents/{dep}/wearable/sync", json={"readings": readings}, headers=auth(token))


def hr(value, ago_s=0, metric="heart_rate"):
    return {"metric_type": metric, "value": value, "recorded_at": (datetime.now(timezone.utc) - timedelta(seconds=ago_s)).isoformat()}


def band(client, token, dep):
    r = client.get(f"/dependents/{dep}/wearable", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def events(db, dep, kind=wearable_service.NO_DATA, status=None):
    db.expire_all()
    q = select(EscalationEvent).where(EscalationEvent.dependent_id == dep, EscalationEvent.trigger_type == kind)
    if status:
        q = q.where(EscalationEvent.status == status)
    return list(db.scalars(q))


def audits(db, action):
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))


def readings(db, dep):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(VitalReading).where(VitalReading.dependent_id == dep, VitalReading.source == "wearable"))


# ------------------------------------------------------------ pairing

def test_dependent_pairs_and_status_starts_waiting(client, store, db):
    t = team(client)
    assert band(client, t["dt"], t["dep"])["status"] == "not_paired"
    r = pair(client, t["dt"], t["dep"], ble_address="c4-5b-be-12-34-56", name="Humsafar band")
    j = ok(r)
    assert j["ble_address"] == ADDR and j["name"] == "Humsafar band" and j["last_sync_at"] is None
    s = band(client, t["pt"], t["dep"])
    assert s["status"] == "waiting_for_first_data" and s["device"]["device_id"] == j["device_id"] and s["no_data_after_s"] == S.BAND_NO_DATA_AFTER_S
    assert s["latest_heart_rate"] is None and s["no_data_alert_open"] is False
    assert audits(db, "wearable_paired") == 1


def test_pairing_rules(client, store):
    t = team(client)
    ok(pair(client, t["pt"], t["dep"]))  # the Primary may pair too
    ok(pair(client, t["dt"], t["dep"]), 200)  # same band again: nothing changes
    assert_error(pair(client, t["dt"], t["dep"], ble_address="AA:BB:CC:DD:EE:FF"), 409, "BAND_ALREADY_PAIRED")
    assert_error(pair(client, t["st"], t["dep"]), 403, "NOT_PRIMARY_GUARDIAN")
    assert client.post(f"/dependents/{t['dep']}/wearable", json={"ble_address": ADDR}).status_code == 401
    for bad in ("nonsense", "C4:5B:BE:12:34", "C4:5B:BE:12:34:ZZ", "", "C4:5B:BE:12:34:56:78"):
        assert_error(pair(client, t["dt"], t["dep"], ble_address=bad), 422, "VALIDATION_ERROR")
    assert_error(pair(client, t["dt"], t["dep"], name="x" * 61), 422, "VALIDATION_ERROR")


def test_other_dependent_and_stranger_cannot_pair(client, store):
    from tests.test_records import stranger_dependent_token
    t = team(client)
    other, _ = stranger_dependent_token(client, 6)
    assert pair(client, other, t["dep"]).status_code == 403
    assert band(client, t["pt"], t["dep"])["status"] == "not_paired"


def test_unpair_is_safe_to_repeat_and_keeps_readings(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(70)]), 200)
    assert client.delete(f"/dependents/{t['dep']}/wearable", headers=auth(t["st"])).status_code == 403
    assert client.delete(f"/dependents/{t['dep']}/wearable", headers=auth(t["dt"])).status_code == 204
    assert client.delete(f"/dependents/{t['dep']}/wearable", headers=auth(t["dt"])).status_code == 204
    assert band(client, t["pt"], t["dep"])["status"] == "not_paired"
    assert readings(db, t["dep"]) == 1
    assert audits(db, "wearable_unpaired") == 1
    ok(pair(client, t["dt"], t["dep"], ble_address="AA:BB:CC:DD:EE:FF"))  # a new band can be paired now


# ------------------------------------------------------------ sync

def test_sync_stores_readings_and_status_becomes_receiving(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    j = ok(sync(client, t["dt"], t["dep"], [hr(72, 120), hr(75, 60), hr(98, 0, "spo2"), hr(36.4, 0, "temperature")]), 200)
    assert j["received"] == 4 and j["stored"] == 4 and j["duplicates"] == 0 and j["rejected"] == [] and j["last_sync_at"]
    s = band(client, t["pt"], t["dep"])
    assert s["status"] == "receiving" and s["seconds_since_data"] is not None and s["seconds_since_data"] < 60
    assert s["latest_heart_rate"]["value"] == 75 and s["latest_heart_rate"]["source"] == "wearable" and s["latest_heart_rate"]["unit"] == "bpm"
    assert s["latest_heart_rate"]["recorded_by"] is None
    latest = client.get(f"/dependents/{t['dep']}/vitals/latest", headers=auth(t["pt"])).json()["latest"]
    assert latest["heart_rate"]["value"] == 75 and latest["spo2"]["value"] == 98 and latest["temperature"]["value"] == 36.4
    items = vlist(client, t["pt"], t["dep"], metric_type="heart_rate")["items"]
    assert [i["value"] for i in items] == [75, 72]
    assert items[0]["can_delete"] is True  # the Primary may delete band readings
    assert vlist(client, t["dt"], t["dep"], metric_type="heart_rate")["items"][0]["can_delete"] is False


def test_retried_batch_is_stored_once(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    batch = [hr(70, 300), hr(71, 240), hr(72, 180)]
    a = ok(sync(client, t["dt"], t["dep"], batch), 200)
    b = ok(sync(client, t["dt"], t["dep"], batch), 200)
    assert a["stored"] == 3 and b["stored"] == 0 and b["duplicates"] == 3
    same_time = hr(60, 10)
    twin = ok(sync(client, t["dt"], t["dep"], [same_time, {**same_time, "value": 61}]), 200)  # same metric and time twice in one batch
    assert twin["stored"] == 1 and twin["duplicates"] == 1
    assert readings(db, t["dep"]) == 4


def test_parallel_identical_syncs_store_once(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    batch = [hr(70 + i, 600 - 60 * i) for i in range(6)]
    bar = Barrier(5)

    def go(_):
        bar.wait()
        return sync(client, t["dt"], t["dep"], batch).json()["stored"]

    with ThreadPoolExecutor(5) as ex:
        stored = list(ex.map(go, range(5)))
    assert sum(stored) == 6, stored
    assert readings(db, t["dep"]) == 6


def test_bad_readings_are_skipped_not_fatal(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    far_past = (datetime.now(timezone.utc) - timedelta(days=S.WEARABLE_BACKFILL_DAYS + 1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    j = ok(sync(client, t["dt"], t["dep"], [
        hr(72, 100),                                                     # 0 good
        hr(10, 90),                                                      # 1 impossible heart rate
        hr(251, 80),                                                     # 2 too high
        hr(101, 70, "spo2"),                                             # 3 spo2 over 100
        hr(50, 60, "temperature"),                                       # 4 temperature out of range
        {"metric_type": "heart_rate", "value": 70, "recorded_at": far_past},  # 5 too old
        {"metric_type": "heart_rate", "value": 70, "recorded_at": future},    # 6 future
        {"metric_type": "heart_rate", "value": 70, "recorded_at": "2026-10-01T09:00:00"},  # 7 no time zone
        hr(80, 20),                                                      # 8 good
    ]), 200)
    assert j["stored"] == 2 and [r["index"] for r in j["rejected"]] == [1, 2, 3, 4, 5, 6, 7]
    assert all(r["reason"] for r in j["rejected"])
    assert readings(db, t["dep"]) == 2


def test_sync_shape_and_permission_errors(client, store):
    t = team(client)
    assert_error(sync(client, t["dt"], t["dep"], [hr(70)]), 409, "NO_BAND")
    ok(pair(client, t["dt"], t["dep"]))
    assert_error(sync(client, t["dt"], t["dep"], []), 422, "VALIDATION_ERROR")
    assert_error(sync(client, t["dt"], t["dep"], [{"metric_type": "blood_pressure", "value": 120, "recorded_at": utcnow().isoformat()}]), 422, "VALIDATION_ERROR")
    assert_error(sync(client, t["dt"], t["dep"], [{"metric_type": "heart_rate", "value": "x", "recorded_at": utcnow().isoformat()}]), 422, "VALIDATION_ERROR")
    assert_error(sync(client, t["dt"], t["dep"], [{"metric_type": "heart_rate", "value": 70}]), 422, "VALIDATION_ERROR")
    assert_error(sync(client, t["dt"], t["dep"], [hr(70)] * (S.WEARABLE_MAX_BATCH + 1)), 422, "VALIDATION_ERROR")
    for who in ("pt", "st"):  # only the Dependent's own phone sends band data
        assert_error(sync(client, t[who], t["dep"], [hr(70)]), 403, "FORBIDDEN")
    assert client.post(f"/dependents/{t['dep']}/wearable/sync", json={"readings": [hr(70)]}).status_code == 401


def test_status_needs_the_health_records_permission(client, store):
    t = team(client)
    assert client.get(f"/dependents/{t['dep']}/wearable", headers=auth(t["st"])).status_code == 403
    allow(client, t)
    assert client.get(f"/dependents/{t['dep']}/wearable", headers=auth(t["st"])).status_code == 200
    assert client.get(f"/dependents/{t['dep']}/wearable").status_code == 401


# ------------------------------------------------------------ "no data" detection

def test_no_data_event_opens_once_and_closes_on_new_data(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(70, 5)]), 200)
    assert wearable_service.sweep_no_data(db) == 0 and events(db, t["dep"]) == []
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    assert wearable_service.sweep_no_data(db, now=later) == 1
    assert wearable_service.sweep_no_data(db, now=later + timedelta(minutes=5)) == 0  # not twice
    ev = events(db, t["dep"], status="open")
    assert len(ev) == 1 and ev[0].tier == "primary"
    s = band(client, t["pt"], t["dep"])
    assert s["no_data_alert_open"] is True and s["no_data_alert_since"]
    # the status itself is computed from the clock, so it reads no_data as soon as the time is up (here: shrink the limit)
    # a fresh reading closes it
    ok(sync(client, t["dt"], t["dep"], [hr(74, 0)]), 200)
    assert events(db, t["dep"], status="open") == [] and len(events(db, t["dep"], status="resolved")) == 1
    assert band(client, t["pt"], t["dep"])["no_data_alert_open"] is False


def test_old_buffered_data_does_not_hide_a_dead_band(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    assert wearable_service.sweep_no_data(db, now=later) == 1  # never sent anything since pairing
    # the phone uploads readings the band measured two hours ago: not new, the band is still silent
    ok(sync(client, t["dt"], t["dep"], [hr(70, 7200)]), 200)
    assert len(events(db, t["dep"], status="open")) == 1
    ok(sync(client, t["dt"], t["dep"], [hr(70, 3)]), 200)
    assert events(db, t["dep"], status="open") == []


def test_never_synced_band_counts_from_pairing(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    assert wearable_service.sweep_no_data(db) == 0
    d = db.scalar(select(WearableDevice).where(WearableDevice.dependent_id == t["dep"]))
    d.paired_at = datetime.now(timezone.utc) - timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 30)
    db.commit()
    assert band(client, t["pt"], t["dep"])["status"] == "no_data"
    assert wearable_service.sweep_no_data(db) == 1


def test_status_reads_no_data_by_the_clock(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(70, 5)]), 200)
    d = db.scalar(select(WearableDevice).where(WearableDevice.dependent_id == t["dep"]))
    d.last_sync_at = datetime.now(timezone.utc) - timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 30)
    db.commit()
    s = band(client, t["pt"], t["dep"])
    assert s["status"] == "no_data" and s["seconds_since_data"] > S.BAND_NO_DATA_AFTER_S


def test_no_alert_while_the_phone_is_offline(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    send(client, t, at=utcnow() - timedelta(seconds=S.DEVICE_OFFLINE_AFTER_S + 120))  # phone went quiet
    from app.services.device_health_service import sweep_offline
    assert sweep_offline(db) == 1 and len(events(db, t["dep"], OFFLINE, "open")) == 1
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    assert wearable_service.sweep_no_data(db, now=later) == 0 and events(db, t["dep"]) == []


def test_unpair_closes_the_alert_and_unpaired_band_is_never_flagged(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    assert wearable_service.sweep_no_data(db, now=later) == 1
    assert client.delete(f"/dependents/{t['dep']}/wearable", headers=auth(t["pt"])).status_code == 204
    assert events(db, t["dep"], status="open") == []
    assert wearable_service.sweep_no_data(db, now=later) == 0


def test_notification_is_standard_and_goes_to_the_right_people(client, store, db):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    assert wearable_service.sweep_no_data(db, now=later) == 1
    notification_service.dispatch_events(db)
    db.expire_all()
    notes = list(db.scalars(select(Notification).where(Notification.type == wearable_service.NO_DATA)))
    assert len(notes) == 1  # the Primary only: the Secondary has no health_records yet
    assert notes[0].priority == "standard" and "band" in notes[0].payload["title"].lower() and "band" in notes[0].payload["body"].lower()
    allow(client, t)  # now the Secondary may see health data, but was not told about the earlier event
    notification_service.dispatch_events(db)
    db.expire_all()
    assert len(list(db.scalars(select(Notification).where(Notification.type == wearable_service.NO_DATA)))) == 2
    ok(sync(client, t["dt"], t["dep"], [hr(70, 1)]), 200)
    notification_service.dispatch_events(db)
    db.expire_all()
    done = list(db.scalars(select(Notification).where(Notification.type == wearable_service.NO_DATA)))
    assert len(done) == 4 and sum(n.priority == "standard" for n in done) == 4  # 2 told + 2 all-clear
    inbox = client.get("/notifications", headers=auth(t["pt"])).json()["items"]
    assert any(i["type"] == "band_no_data" and i["priority"] == "standard" for i in inbox)


def test_band_alert_does_not_climb_the_escalation_chain(client, store, db):
    from app.services import escalation_service
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    later = datetime.now(timezone.utc) + timedelta(seconds=S.BAND_NO_DATA_AFTER_S + 60)
    wearable_service.sweep_no_data(db, now=later)
    assert "band_no_data" not in escalation_service.ESCALATING


# ------------------------------------------------------------ demo data

def test_mock_data_makes_demo_readings(client, store, db):
    t = team(client)
    assert_error(client.post(f"/dependents/{t['dep']}/wearable/mock", headers=auth(t["dt"])), 409, "NO_BAND")
    ok(pair(client, t["dt"], t["dep"]))
    j = ok(client.post(f"/dependents/{t['dep']}/wearable/mock", json={"count": 20, "interval_s": 30}, headers=auth(t["dt"])), 200)
    assert j["stored"] == 20 and j["rejected"] == []
    items = vlist(client, t["pt"], t["dep"], metric_type="heart_rate", limit=50)["items"]
    assert len(items) == 20 and all(52 <= i["value"] <= 110 and i["note"] == "mock band data" for i in items)
    assert band(client, t["pt"], t["dep"])["status"] == "receiving"
    d = ok(client.post(f"/dependents/{t['dep']}/wearable/mock", headers=auth(t["pt"])), 200)  # default body, the Primary may too
    assert d["received"] == 30 and d["stored"] + d["duplicates"] == 30 and d["stored"] >= 20  # same-second samples are not stored twice
    assert_error(client.post(f"/dependents/{t['dep']}/wearable/mock", headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert client.post(f"/dependents/{t['dep']}/wearable/mock", json={"count": 201}, headers=auth(t["dt"])).status_code == 422


def test_mock_can_be_switched_off(client, store, monkeypatch):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    monkeypatch.setattr(S, "WEARABLE_MOCK_ENABLED", False, raising=False)
    assert_error(client.post(f"/dependents/{t['dep']}/wearable/mock", headers=auth(t["dt"])), 404, "NOT_FOUND")


# ------------------------------------------------------------ rules in the database, retention, exports

def test_typed_readings_cannot_use_band_only_metrics_in_the_database(client, store, db):
    from sqlalchemy.exc import IntegrityError
    t = team(client)
    import uuid
    db.add(VitalReading(dependent_id=uuid.UUID(t["dep"]), metric_type="heart_rate", value=70, source="manual"))
    try:
        db.commit()
        raised = False
    except IntegrityError:
        db.rollback()
        raised = True
    assert raised
    assert_error(vadd(client, t["dt"], t["dep"], metric_type="heart_rate", value=70), 422, "VALIDATION_ERROR")


def test_old_band_readings_are_purged_by_the_job(client, store, db, monkeypatch):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(70, 10)]), 200)
    import uuid
    db.add(VitalReading(dependent_id=uuid.UUID(t["dep"]), metric_type="heart_rate", value=65, source="wearable",
                        recorded_at=datetime.now(timezone.utc) - timedelta(days=S.WEARABLE_RETENTION_DAYS + 5)))
    db.add(VitalReading(dependent_id=uuid.UUID(t["dep"]), metric_type="spo2", value=97, source="manual",
                        recorded_at=datetime.now(timezone.utc) - timedelta(days=S.WEARABLE_RETENTION_DAYS + 5)))
    db.commit()
    monkeypatch.setattr(wearable_service, "_last_purge", None)
    wearable_service.sweep_no_data(db)
    db.expire_all()
    left = list(db.scalars(select(VitalReading).where(VitalReading.dependent_id == uuid.UUID(t["dep"]))))
    assert sorted((r.source, r.metric_type) for r in left) == [("manual", "spo2"), ("wearable", "heart_rate")]  # typed readings are never purged


def test_pdf_has_a_daily_band_summary_not_every_reading(client, store):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(60, 300), hr(80, 240), hr(100, 180)]), 200)
    ok(vadd(client, t["dt"], t["dep"], value=125, diastolic=81))
    r = client.get(f"/dependents/{t['dep']}/vitals/export", headers=auth(t["pt"]))
    text, _ = pdf_text(r.content)
    assert "125/81 mmHg" in text and "Wearable band" in text
    assert "80.0 bpm" in text and "60 bpm" in text and "100 bpm" in text  # average, lowest, highest
    assert "Wearable band" in pdf_text(export(client, t["pt"], t["dep"], include_vitals="true").content)[0]
    assert "u00b0" not in text


def test_band_only_pdf_still_works(client, store):
    t = team(client)
    ok(pair(client, t["dt"], t["dep"]))
    ok(sync(client, t["dt"], t["dep"], [hr(72, 60)]), 200)
    r = client.get(f"/dependents/{t['dep']}/vitals/export", headers=auth(t["pt"]))
    assert r.status_code == 200
    text, _ = pdf_text(r.content)
    assert "No typed readings" in text and "Heart rate" in text
