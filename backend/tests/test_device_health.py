"""
Task 2.3 tests: battery monitoring (FR-L1), connectivity-loss detection (FR-L2), device-health read, scheduler.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core import scheduler
from app.core.config import get_settings
from app.models import EscalationEvent
from app.services import device_health_service
from app.services.device_health_service import LOW_BATTERY, OFFLINE, sweep_offline
from tests.test_linkage import assert_error, auth, link, make_dependent, make_guardian
from tests.test_location import LAT, LNG, send, team, utcnow
from tests.test_permissions import put

S = get_settings()


def events(db, dep, kind, status=None):
    db.expire_all()
    q = select(EscalationEvent).where(EscalationEvent.dependent_id == dep, EscalationEvent.trigger_type == kind)
    if status:
        q = q.where(EscalationEvent.status == status)
    return list(db.scalars(q))


def fix(client, t, battery=None, ago=0, lat=LAT, **extra):
    if battery is not None:
        extra["battery_level"] = battery
    return send(client, t, lat=lat, at=utcnow() - timedelta(seconds=ago), **extra)


def health(client, t, token="pt"):
    r = client.get(f"/dependents/{t['dep']}/device-health", headers=auth(t[token]))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------ battery (FR-L1)

def test_low_battery_opens_one_alert_at_15_percent(client, db):
    t = team(client)
    ok = fix(client, t, 40, ago=120).json()
    assert ok["low_battery"] is False and ok["low_battery_started"] is False
    assert events(db, t["dep"], LOW_BATTERY) == []
    first = fix(client, t, 15, ago=60).json()  # exactly 15%: the SRS says "falls to 15%"
    assert first["low_battery"] is True and first["low_battery_started"] is True
    again = fix(client, t, 14, ago=30).json()
    assert again["low_battery"] is True and again["low_battery_started"] is False  # no second alert
    assert fix(client, t, 9, ago=0).json()["low_battery_started"] is False
    ev = events(db, t["dep"], LOW_BATTERY)
    assert len(ev) == 1 and ev[0].status == "open" and ev[0].tier == "primary"


def test_battery_alert_closes_only_when_charged_above_20(client, db):
    t = team(client)
    fix(client, t, 12, ago=300)
    assert len(events(db, t["dep"], LOW_BATTERY, "open")) == 1
    for pct, ago in ((16, 240), (18, 180), (20, 120)):  # creeping up: still open (no flapping)
        assert fix(client, t, pct, ago=ago).json()["low_battery"] is True
    assert len(events(db, t["dep"], LOW_BATTERY, "open")) == 1
    r = fix(client, t, 21, ago=60).json()
    assert r["low_battery"] is False
    ev = events(db, t["dep"], LOW_BATTERY)
    assert len(ev) == 1 and ev[0].status == "resolved" and ev[0].resolved_at is not None
    # draining again is a NEW alert
    assert fix(client, t, 15, ago=0).json()["low_battery_started"] is True
    assert len(events(db, t["dep"], LOW_BATTERY)) == 2


def test_fix_without_a_battery_reading_changes_nothing(client, db):
    t = team(client)
    fix(client, t, 10, ago=120)
    r = fix(client, t, None, ago=60, lat=LAT + 0.001).json()
    assert r["low_battery"] is True  # still open: a missing reading does not close it
    assert len(events(db, t["dep"], LOW_BATTERY, "open")) == 1


def test_late_buffered_fix_cannot_change_battery_state(client, db):
    t = team(client)
    fix(client, t, 80, ago=10)  # newest: healthy
    late = fix(client, t, 5, ago=900).json()  # an old low reading arrives late
    assert late["low_battery_started"] is False and events(db, t["dep"], LOW_BATTERY) == []
    fix(client, t, 10, ago=0)  # now genuinely low
    fix(client, t, 90, ago=600)  # an old high reading arrives late
    assert len(events(db, t["dep"], LOW_BATTERY, "open")) == 1  # not closed by the stale fix


def test_retrying_the_low_battery_fix_does_not_double_count(client, db):
    t = team(client)
    at = utcnow() - timedelta(seconds=20)
    a = send(client, t, at=at, battery_level=10).json()
    b = send(client, t, at=at, battery_level=10).json()
    assert a["low_battery_started"] is True and b["duplicate"] is True and b["low_battery_started"] is False
    assert len(events(db, t["dep"], LOW_BATTERY)) == 1


def test_low_battery_asks_the_phone_to_check_in_more_often(client):
    t = team(client)
    base = utcnow() - timedelta(minutes=40)
    send(client, t, at=base, battery_level=60)
    for i in range(1, 14):  # stay put until idle: normally a 180 s wait
        r = send(client, t, at=base + timedelta(seconds=60 * i), battery_level=60).json()
    assert r["movement_state"] == "idle" and r["next_update_interval_s"] == S.LOCATION_INTERVAL_IDLE_S
    low = send(client, t, at=base + timedelta(seconds=60 * 14), battery_level=12).json()
    assert low["movement_state"] == "idle" and low["next_update_interval_s"] == S.LOCATION_INTERVAL_LOW_BATTERY_S


def test_battery_range_is_still_validated(client):
    t = team(client)
    assert send(client, t, battery_level=101).status_code == 422
    assert send(client, t, battery_level=-1).status_code == 422


# ------------------------------------------------------------ connectivity (FR-L2)

def test_silent_phone_is_flagged_once_after_the_threshold(client, db):
    t = team(client)
    fix(client, t, 70, ago=S.DEVICE_OFFLINE_AFTER_S - 60)  # last heard 9 minutes ago: still fine
    assert sweep_offline(db) == 0 and events(db, t["dep"], OFFLINE) == []
    later = datetime.now(timezone.utc) + timedelta(minutes=3)  # 12 minutes of silence
    assert sweep_offline(db, now=later) == 1
    ev = events(db, t["dep"], OFFLINE)
    assert len(ev) == 1 and ev[0].status == "open"
    assert sweep_offline(db, now=later + timedelta(minutes=5)) == 0  # a second sweep must not add another
    assert len(events(db, t["dep"], OFFLINE)) == 1
    assert events(db, t["dep"], LOW_BATTERY) == []  # distinct from the battery alert


def test_a_new_fix_closes_the_offline_alert(client, db):
    t = team(client)
    fix(client, t, 70, ago=S.DEVICE_OFFLINE_AFTER_S + 120)
    assert sweep_offline(db) == 1
    r = fix(client, t, 70, ago=0)
    assert r.status_code == 200
    ev = events(db, t["dep"], OFFLINE)
    assert len(ev) == 1 and ev[0].status == "resolved" and ev[0].resolved_at is not None
    assert sweep_offline(db) == 0  # fresh again
    # going quiet a second time is a NEW alert
    assert sweep_offline(db, now=datetime.now(timezone.utc) + timedelta(minutes=15)) == 1
    assert len(events(db, t["dep"], OFFLINE)) == 2


def test_never_reported_and_unlinked_dependents_are_not_flagged(client, db):
    t = team(client)  # linked, but never sent a fix
    assert sweep_offline(db, now=datetime.now(timezone.utc) + timedelta(days=3)) == 0
    assert events(db, t["dep"], OFFLINE) == []


def test_offline_is_per_dependent(client, db):
    t = team(client)
    fix(client, t, 70, ago=S.DEVICE_OFFLINE_AFTER_S + 60)
    pt2, _, _ = make_guardian(client, 8)
    dep2 = make_dependent(client, 3)
    assert link(client, pt2, dep2).status_code == 201
    assert sweep_offline(db) == 1
    assert len(events(db, t["dep"], OFFLINE)) == 1 and events(db, dep2, OFFLINE) == []


def test_simultaneous_sweeps_open_exactly_one_alert(client, db, engine, monkeypatch):
    t = team(client)
    fix(client, t, 70, ago=S.DEVICE_OFFLINE_AFTER_S + 60)
    barrier = threading.Barrier(2)
    original = device_health_service._open_event

    def paused(db_, dep, kind, lock=False):
        ev = original(db_, dep, kind, lock)
        if not lock and kind == OFFLINE:
            try:
                barrier.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
        return ev

    monkeypatch.setattr(device_health_service, "_open_event", paused)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def run(_):
        s = Session()
        try:
            return sweep_offline(s)
        finally:
            s.close()

    with ThreadPoolExecutor(2) as ex:
        opened = list(ex.map(run, range(2)))
    assert sum(opened) == 1, opened
    assert len(events(db, t["dep"], OFFLINE, "open")) == 1


# ------------------------------------------------------------ the read endpoint

def test_device_health_before_any_fix(client):
    t = team(client)
    h = health(client, t)
    assert h["connectivity"] == "unknown" and h["battery_level"] is None and h["last_known_location"] is None
    assert h["low_battery"] is False and h["offline_alert_open"] is False and h["probable_cause"] is None
    assert h["thresholds"] == {"low_battery_pct": 15, "battery_recover_pct": 20, "offline_after_s": 600}


def test_device_health_online_with_battery(client):
    t = team(client)
    fix(client, t, 64, ago=20)
    h = health(client, t)
    assert h["connectivity"] == "online" and h["battery_level"] == 64 and h["low_battery"] is False
    assert 0 <= h["seconds_since_seen"] < 120 and h["last_known_location"]["lat"] == LAT


def test_battery_comes_from_the_newest_fix_that_had_one(client):
    t = team(client)
    fix(client, t, 55, ago=120)
    fix(client, t, None, ago=30, lat=LAT + 0.01)  # newer fix, no battery reading
    h = health(client, t)
    assert h["battery_level"] == 55 and h["last_known_location"]["lat"] == LAT + 0.01


def test_offline_with_a_dead_battery_is_labelled(client, db):
    t = team(client)
    fix(client, t, 3, ago=S.DEVICE_OFFLINE_AFTER_S + 300)  # last words: 3%
    sweep_offline(db)
    h = health(client, t)
    assert h["connectivity"] == "offline" and h["offline_alert_open"] is True
    assert h["probable_cause"] == "battery_depleted" and h["low_battery"] is True
    assert h["last_known_location"] is not None  # FR-L1.3: where they were


def test_offline_with_a_healthy_battery_is_labelled_connectivity(client, db):
    t = team(client)
    fix(client, t, 80, ago=S.DEVICE_OFFLINE_AFTER_S + 300)
    sweep_offline(db)
    h = health(client, t)
    assert h["connectivity"] == "offline" and h["probable_cause"] == "connectivity_or_unknown"


def test_secondary_needs_live_location_to_read_device_health(client):
    t = team(client)
    fix(client, t, 50)
    url = f"/dependents/{t['dep']}/device-health"
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], True).status_code == 200
    assert client.get(url, headers=auth(t["st"])).status_code == 200
    put(client, t["pt"], t["dep"], "live_location", t["sid"], False)
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")  # revoke is immediate


def test_outsiders_dependent_and_anonymous_cannot_read(client):
    t = team(client)
    outsider, _, _ = make_guardian(client, 7)
    url = f"/dependents/{t['dep']}/device-health"
    assert_error(client.get(url, headers=auth(outsider)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(url, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert_error(client.get(url), 401, "NOT_AUTHENTICATED")
    assert_error(client.get("/dependents/not-a-uuid/device-health", headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ scheduler

def test_scheduler_runs_jobs_and_survives_a_failing_one(client, db, engine, monkeypatch):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(scheduler, "SessionLocal", Session)
    t = team(client)
    fix(client, t, 70, ago=S.DEVICE_OFFLINE_AFTER_S + 120)

    def boom(_db):
        raise RuntimeError("bad job")

    monkeypatch.setattr(scheduler, "JOBS", scheduler.JOBS + [("boom", boom)])
    res = scheduler.run_jobs_once()
    assert res["device_offline_sweep"] == "ok" and res["boom"].startswith("error")
    assert len(events(db, t["dep"], OFFLINE, "open")) == 1  # the real job still did its work


def test_scheduler_is_off_in_tests(client):
    assert get_settings().SCHEDULER_ENABLED is False
