"""
Task 2.1 tests: location ingestion, adaptive frequency, latest/history reads (FR-C1, FR-C4).
"""

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models import LocationLog
from app.services import location_service
from app.services.location_service import classify_movement, haversine_m
from tests.test_linkage import (
    PASSWORD,
    PHOTO,
    assert_error,
    auth,
    link,
    login,
    make_dependent,
    make_guardian,
    make_secondary,
)
from tests.test_permissions import put, verify

# Karachi. 0.001 degrees of latitude is about 111 m.
LAT, LNG = 24.8607, 67.0011


def utcnow():
    # Always fresh: the full suite runs for minutes, so a module-level constant would go stale.
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def team(client):
    """Verified Primary, an activated Dependent (token), and a verified Secondary."""
    pt, pid, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    k = client.post(
        f"/dependents/{dep}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-7654321-1", "liveness_image": PHOTO}
    )
    assert k.json()["status"] == "verified"
    assert link(client, pt, dep).status_code == 201
    dt, _ = login(client, "d1@link-test.com")
    st, sid, _ = make_secondary(client, pt, dep, 1)
    verify(client, st)
    return {"pt": pt, "dep": dep, "dt": dt, "st": st, "sid": sid}


def send(client, t, lat=LAT, lng=LNG, at=None, **extra):
    body = {"lat": lat, "lng": lng, **extra}
    if at is not None:
        body["recorded_at"] = iso(at)
    return client.post(f"/dependents/{t['dep']}/location", json=body, headers=auth(t["dt"]))


# ------------------------------------------------------------ pure logic

def test_haversine_known_distance():
    assert 105 < haversine_m(LAT, LNG, LAT + 0.001, LNG) < 117


def test_first_fix_counts_as_moving():
    assert classify_movement(LAT, LNG, utcnow(), []) == "moving"


def test_gps_jitter_is_not_movement():
    prev = [(LAT + 0.0001, LNG, utcnow() - timedelta(seconds=60))]  # about 11 m
    assert classify_movement(LAT, LNG, utcnow(), prev) == "stationary"


def test_real_displacement_is_movement():
    prev = [(LAT + 0.001, LNG, utcnow() - timedelta(seconds=60))]  # about 111 m
    assert classify_movement(LAT, LNG, utcnow(), prev) == "moving"


def test_speed_alone_means_moving():
    prev = [(LAT, LNG, utcnow() - timedelta(seconds=60))]
    assert classify_movement(LAT, LNG, utcnow(), prev, speed_mps=1.5) == "moving"
    assert classify_movement(LAT, LNG, utcnow(), prev, speed_mps=0.1) == "stationary"


def test_poor_accuracy_hides_small_shifts():
    prev = [(LAT + 0.0005, LNG, utcnow() - timedelta(seconds=60))]  # about 55 m
    assert classify_movement(LAT, LNG, utcnow(), prev) == "moving"
    assert classify_movement(LAT, LNG, utcnow(), prev, accuracy_m=200) == "stationary"


def test_long_stay_becomes_idle_and_a_move_resets_it():
    s = get_settings()
    t0 = utcnow() - timedelta(seconds=s.LOCATION_IDLE_AFTER_S + 60)
    still = [(LAT, LNG, utcnow() - timedelta(seconds=60 * i)) for i in range(1, 12)]  # newest first, 11 minutes
    assert classify_movement(LAT, LNG, utcnow(), still) == "idle"
    # the oldest fixes were somewhere else: the stay is shorter than the idle window
    moved = still[:4] + [(LAT + 0.01, LNG, t0)]
    assert classify_movement(LAT, LNG, utcnow(), moved) == "stationary"


# ------------------------------------------------------------ ingestion

def test_dependent_sends_a_fix_and_gets_the_interval(client, db):
    t = team(client)
    r = send(client, t, battery_level=80)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movement_state"] == "moving"  # first fix
    assert body["next_update_interval_s"] == get_settings().LOCATION_INTERVAL_MOVING_S
    assert body["duplicate"] is False
    row = db.get(LocationLog, body["log_id"])
    assert row.lat == LAT and row.lng == LNG and row.battery_level == 80


def test_interval_adapts_as_the_dependent_stops_and_stays(client):
    t = team(client)
    s = get_settings()
    base = utcnow() - timedelta(minutes=30)
    send(client, t, at=base)
    walking = send(client, t, lat=LAT + 0.002, at=base + timedelta(seconds=30))
    assert walking.json()["movement_state"] == "moving"
    assert walking.json()["next_update_interval_s"] == s.LOCATION_INTERVAL_MOVING_S
    still = send(client, t, lat=LAT + 0.002, at=base + timedelta(seconds=90))
    assert still.json()["movement_state"] == "stationary"
    assert still.json()["next_update_interval_s"] == s.LOCATION_INTERVAL_STATIONARY_S
    for i in range(2, 14):
        last = send(client, t, lat=LAT + 0.002, at=base + timedelta(seconds=90 + 60 * i))
    assert last.json()["movement_state"] == "idle"
    assert last.json()["next_update_interval_s"] == s.LOCATION_INTERVAL_IDLE_S
    again = send(client, t, lat=LAT + 0.01, at=base + timedelta(seconds=90 + 60 * 14))
    assert again.json()["movement_state"] == "moving"  # moving resets straight to the short interval


def test_retrying_the_same_fix_does_not_store_it_twice(client, db):
    t = team(client)
    at = utcnow() - timedelta(seconds=30)
    first = send(client, t, at=at).json()
    second = send(client, t, at=at).json()
    assert second["duplicate"] is True and second["log_id"] == first["log_id"]
    assert db.query(LocationLog).count() == 1


def test_late_arriving_fix_is_stored_in_order(client):
    t = team(client)
    send(client, t, lat=LAT, at=utcnow() - timedelta(minutes=2))
    send(client, t, lat=LAT + 0.01, at=utcnow() - timedelta(minutes=1))
    send(client, t, lat=LAT + 0.005, at=utcnow() - timedelta(seconds=90))  # arrives late, belongs in the middle
    pts = client.get(f"/dependents/{t['dep']}/location/history", headers=auth(t["pt"])).json()["points"]
    times = [p["recorded_at"] for p in pts]
    assert len(pts) == 3 and times == sorted(times, reverse=True)


def test_validation_rejects_bad_input(client):
    t = team(client)
    for bad in (
        {"lat": 91, "lng": 0}, {"lat": 0, "lng": 181}, {"lat": "x", "lng": 0}, {"lat": 0},
        {"lat": 0, "lng": 0, "battery_level": 101}, {"lat": 0, "lng": 0, "battery_level": -1},
        {"lat": 0, "lng": 0, "speed_mps": -1}, {"lat": 0, "lng": 0, "accuracy_m": -5},
        {"lat": 0, "lng": 0, "recorded_at": "2026-10-16T09:30:00"},  # no timezone
    ):
        r = client.post(f"/dependents/{t['dep']}/location", json=bad, headers=auth(t["dt"]))
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["error"]["code"] == "VALIDATION_ERROR", bad
    # NaN / Infinity are not valid JSON numbers for our API, and must never reach the database
    raw = client.post(
        f"/dependents/{t['dep']}/location", content='{"lat": NaN, "lng": 0}',
        headers={**auth(t["dt"]), "Content-Type": "application/json"},
    )
    assert raw.status_code == 422


def test_timestamp_limits(client):
    t = team(client)
    assert_error(send(client, t, at=utcnow() + timedelta(hours=1)), 422, "TIMESTAMP_IN_FUTURE")
    assert_error(send(client, t, at=utcnow() - timedelta(days=2)), 422, "TIMESTAMP_TOO_OLD")
    assert send(client, t, at=utcnow() + timedelta(seconds=30)).status_code == 200  # small clock skew is fine


def test_only_the_dependent_themself_can_send(client):
    t = team(client)
    body = {"lat": LAT, "lng": LNG}
    # a guardian (even the Primary)
    assert_error(client.post(f"/dependents/{t['dep']}/location", json=body, headers=auth(t["pt"])), 403, "FORBIDDEN")
    # another Dependent
    other = make_dependent(client, 2)
    assert_error(client.post(f"/dependents/{other}/location", json=body, headers=auth(t["dt"])), 403, "FORBIDDEN")
    # no token
    assert_error(client.post(f"/dependents/{t['dep']}/location", json=body), 401, "NOT_AUTHENTICATED")


# ------------------------------------------------------------ reading + permissions

def test_primary_reads_latest_location(client):
    t = team(client)
    empty = client.get(f"/dependents/{t['dep']}/location", headers=auth(t["pt"])).json()
    assert empty["location"] is None and empty["is_stale"] is True and empty["age_seconds"] is None
    send(client, t, lat=LAT, at=utcnow() - timedelta(seconds=40), battery_level=70)
    send(client, t, lat=LAT + 0.01, at=utcnow() - timedelta(seconds=10), battery_level=69)
    got = client.get(f"/dependents/{t['dep']}/location", headers=auth(t["pt"])).json()
    assert got["location"]["lat"] == LAT + 0.01 and got["location"]["battery_level"] == 69
    assert 0 <= got["age_seconds"] < 60 and got["is_stale"] is False


def test_old_fix_is_marked_stale(client):
    t = team(client)
    send(client, t, at=utcnow() - timedelta(hours=2))
    got = client.get(f"/dependents/{t['dep']}/location", headers=auth(t["pt"])).json()
    assert got["is_stale"] is True and got["age_seconds"] >= 7000


def test_secondary_needs_the_live_location_grant_and_revoke_is_immediate(client):
    t = team(client)
    send(client, t)
    url = f"/dependents/{t['dep']}/location"
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], True).status_code == 200
    assert client.get(url, headers=auth(t["st"])).status_code == 200
    assert client.get(url + "/history", headers=auth(t["st"])).status_code == 200
    # another module does not unlock location
    put(client, t["pt"], t["dep"], "live_location", t["sid"], False)
    put(client, t["pt"], t["dep"], "camera_viewing", t["sid"], True)
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(url + "/history", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")


def test_unlinked_guardian_and_the_dependent_cannot_read(client):
    t = team(client)
    outsider, _, _ = make_guardian(client, 7)
    url = f"/dependents/{t['dep']}/location"
    assert_error(client.get(url, headers=auth(outsider)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(url, headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert_error(client.get(url), 401, "NOT_AUTHENTICATED")


def test_location_is_per_dependent(client):
    t = team(client)
    send(client, t)
    other = make_dependent(client, 2)
    assert_error(client.get(f"/dependents/{other}/location", headers=auth(t["pt"])), 403, "NOT_LINKED_TO_DEPENDENT")


# ------------------------------------------------------------ history

def test_history_order_range_and_limit(client):
    t = team(client)
    for i in range(6):
        send(client, t, lat=LAT + i * 0.001, at=utcnow() - timedelta(minutes=10 - i))
    url = f"/dependents/{t['dep']}/location/history"
    h = auth(t["pt"])
    allp = client.get(url, headers=h).json()
    assert allp["count"] == 6 and allp["points"][0]["lat"] == LAT + 5 * 0.001  # newest first
    assert client.get(url, params={"limit": 2}, headers=h).json()["count"] == 2
    window = client.get(
        url, params={"from": iso(utcnow() - timedelta(minutes=8, seconds=30)), "to": iso(utcnow() - timedelta(minutes=6, seconds=30))},
        headers=h,
    ).json()
    assert window["count"] == 2
    assert_error(
        client.get(url, params={"from": iso(utcnow()), "to": iso(utcnow() - timedelta(hours=1))}, headers=h), 422, "INVALID_RANGE"
    )
    assert client.get(url, params={"limit": 501}, headers=h).status_code == 422
    assert client.get(url, params={"limit": 0}, headers=h).status_code == 422


def test_history_keeps_dependents_apart(client):
    t = team(client)
    send(client, t)
    pt2, _, _ = make_guardian(client, 8)
    dep2 = make_dependent(client, 3)
    assert link(client, pt2, dep2).status_code == 201
    assert client.get(f"/dependents/{dep2}/location/history", headers=auth(pt2)).json()["count"] == 0
