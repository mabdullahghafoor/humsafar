"""
Task 2.2 tests: geofence CRUD (FR-C2, FR-C3) and breach detection.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.models import EscalationEvent, Geofence
from app.schemas.geofence import MAX_RADIUS_M, MIN_RADIUS_M
from app.services import geofence_service, linkage_service
from app.services.geofence_service import MAX_ZONES, evaluate
from tests.test_linkage import assert_error, auth, link, make_dependent, make_guardian
from tests.test_location import LAT, LNG, iso, send, team, utcnow
from tests.test_permissions import put

# 0.001 degrees of latitude = about 111 m
HOME = (LAT, LNG)
FAR = (LAT + 0.05, LNG)  # about 5.5 km away


def zone(name="Home", lat=LAT, lng=LNG, radius=200):
    return {"name": name, "lat": lat, "lng": lng, "radius_m": radius}


def add(client, t, **kw):
    return client.post(f"/dependents/{t['dep']}/geofences", json=zone(**kw), headers=auth(t["pt"]))


def breaches(db, dep, status=None):
    db.expire_all()
    q = select(EscalationEvent).where(EscalationEvent.dependent_id == dep, EscalationEvent.trigger_type == "geofence_breach")
    if status:
        q = q.where(EscalationEvent.status == status)
    return list(db.scalars(q))


def fix(client, t, where, seconds_ago=0, **extra):
    return send(client, t, lat=where[0], lng=where[1], at=utcnow() - timedelta(seconds=seconds_ago), **extra)


# ------------------------------------------------------------ pure logic

def G(lat, lng, radius):
    return SimpleNamespace(geofence_id=f"{lat}-{lng}-{radius}", lat=lat, lng=lng, radius_m=radius)


def test_no_zones_means_nothing_to_breach():
    assert evaluate([], *FAR) == ("no_zones", [])


def test_inside_any_zone_is_safe_outside_all_is_breach():
    home, relative = G(*HOME, 200), G(LAT + 0.05, LNG, 200)
    assert evaluate([home, relative], *HOME)[0] == "inside"
    assert evaluate([home, relative], *FAR)[0] == "inside"  # inside the SECOND zone (FR-C3.2)
    assert evaluate([home, relative], LAT + 0.025, LNG)[0] == "outside"  # between them


def test_zone_edge_and_gps_error():
    z = G(*HOME, 200)
    just_out = (LAT + 0.0020, LNG)  # about 222 m from the centre
    assert evaluate([z], *just_out)[0] == "outside"
    assert evaluate([z], *just_out, accuracy_m=50)[0] == "inside"  # within the GPS error: no false alarm
    way_out = (LAT + 0.01, LNG)  # about 1.1 km
    assert evaluate([z], *way_out, accuracy_m=5000)[0] == "outside"  # the allowance is capped at 100 m


# ------------------------------------------------------------ CRUD and permissions

def test_primary_creates_lists_updates_and_deletes_zones(client):
    t = team(client)
    r = add(client, t, name="  Home  ")
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["name"] == "Home" and g["radius_m"] == 200 and g["dependent_id"] == t["dep"]
    lst = client.get(f"/dependents/{t['dep']}/geofences", headers=auth(t["pt"])).json()
    assert lst["count"] == 1 and lst["max_zones"] == MAX_ZONES and lst["geofences"][0]["geofence_id"] == g["geofence_id"]
    url = f"/dependents/{t['dep']}/geofences/{g['geofence_id']}"
    up = client.put(url, json=zone("Clinic", LAT + 0.01, LNG, 500), headers=auth(t["pt"]))
    assert up.status_code == 200 and up.json()["name"] == "Clinic" and up.json()["radius_m"] == 500
    assert client.delete(url, headers=auth(t["pt"])).status_code == 204
    assert client.get(f"/dependents/{t['dep']}/geofences", headers=auth(t["pt"])).json()["count"] == 0
    assert_error(client.delete(url, headers=auth(t["pt"])), 404, "GEOFENCE_NOT_FOUND")


def test_secondary_can_view_but_never_change_zones(client):
    t = team(client)
    g = add(client, t).json()
    url = f"/dependents/{t['dep']}/geofences"
    one = f"{url}/{g['geofence_id']}"
    # no grant: cannot even view
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    put(client, t["pt"], t["dep"], "live_location", t["sid"], True)
    assert client.get(url, headers=auth(t["st"])).status_code == 200
    assert client.get(f"/dependents/{t['dep']}/geofence-status", headers=auth(t["st"])).status_code == 200
    # even with live_location: no write access (FR-C2.1)
    assert_error(client.post(url, json=zone(), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.put(one, json=zone("x"), headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.delete(one, headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")


def test_other_guardians_dependents_and_anonymous_are_refused(client):
    t = team(client)
    g = add(client, t).json()
    outsider, _, _ = make_guardian(client, 7)
    base = f"/dependents/{t['dep']}/geofences"
    assert_error(client.post(base, json=zone(), headers=auth(outsider)), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.get(base, headers=auth(outsider)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(base, headers=auth(t["dt"])), 403, "FORBIDDEN")  # the Dependent themself
    assert_error(client.post(base, json=zone(), headers=auth(t["dt"])), 403, "FORBIDDEN")
    assert_error(client.get(base), 401, "NOT_AUTHENTICATED")
    assert_error(client.delete(f"{base}/{g['geofence_id']}"), 401, "NOT_AUTHENTICATED")


def test_a_zone_id_from_another_dependent_is_not_found(client):
    t = team(client)
    pt2, _, _ = make_guardian(client, 8)
    dep2 = make_dependent(client, 3)
    assert link(client, pt2, dep2).status_code == 201
    other_zone = client.post(f"/dependents/{dep2}/geofences", json=zone("Theirs"), headers=auth(pt2)).json()["geofence_id"]
    # t's Primary tries to touch the other Dependent's zone through their own dependent id
    url = f"/dependents/{t['dep']}/geofences/{other_zone}"
    assert_error(client.put(url, json=zone("x"), headers=auth(t["pt"])), 404, "GEOFENCE_NOT_FOUND")
    assert_error(client.delete(url, headers=auth(t["pt"])), 404, "GEOFENCE_NOT_FOUND")
    # and the zone is untouched
    assert client.get(f"/dependents/{dep2}/geofences", headers=auth(pt2)).json()["geofences"][0]["name"] == "Theirs"


def test_zone_validation(client):
    t = team(client)
    base = f"/dependents/{t['dep']}/geofences"
    bad = [
        zone(radius=MIN_RADIUS_M - 1), zone(radius=MAX_RADIUS_M + 1), zone(radius=0), zone(radius=-5),
        zone(lat=91), zone(lng=181), zone(name=""), zone(name="   "), zone(name="x" * 101),
        {"name": "x", "lat": 1, "lng": 1}, {"lat": 1, "lng": 1, "radius_m": 100},
    ]
    for body in bad:
        r = client.post(base, json=body, headers=auth(t["pt"]))
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR", body
    assert client.post(base, json=zone(radius=MIN_RADIUS_M), headers=auth(t["pt"])).status_code == 201
    assert client.post(base, json=zone("Big", radius=MAX_RADIUS_M), headers=auth(t["pt"])).status_code == 201


def test_zone_limit(client):
    t = team(client)
    for i in range(MAX_ZONES):
        assert add(client, t, name=f"z{i}").status_code == 201
    r = add(client, t, name="one too many")
    assert_error(r, 409, "GEOFENCE_LIMIT_REACHED")


def test_zone_limit_holds_under_simultaneous_creates(client, db, engine, monkeypatch):
    t = team(client)
    for i in range(MAX_ZONES - 1):
        assert add(client, t, name=f"z{i}").status_code == 201
    # several creates race for the LAST slot; without the row lock more than one would get in
    barrier = threading.Barrier(4)
    original = geofence_service._zones

    def paused(db_, dep):
        zones = original(db_, dep)
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            pass
        return zones

    monkeypatch.setattr(geofence_service, "_zones", paused)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def attempt(i):
        s = Session()
        try:
            from app.models import User
            from app.schemas.geofence import GeofenceIn

            user = s.get(User, __import__("uuid").UUID(security.decode_token(t["pt"], security.ACCESS)["sub"]))
            try:
                geofence_service.create(s, user, __import__("uuid").UUID(t["dep"]), GeofenceIn(**zone(f"race{i}")))
                return "ok"
            except Exception as e:  # AppError
                return getattr(e, "code", repr(e))
        finally:
            s.close()

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(attempt, range(4)))
    assert results.count("ok") == 1, results
    assert results.count("GEOFENCE_LIMIT_REACHED") == 3, results
    db.expire_all()
    assert db.query(Geofence).filter(Geofence.dependent_id == t["dep"]).count() == MAX_ZONES


# ------------------------------------------------------------ breach detection

def test_no_zones_no_breach_however_far(client, db):
    t = team(client)
    r = fix(client, t, FAR)
    assert r.json()["geofence_status"] == "no_zones" and r.json()["breach_started"] is False
    assert breaches(db, t["dep"]) == []


def test_leaving_the_zone_opens_one_breach_and_returning_resolves_it(client, db):
    t = team(client)
    add(client, t, radius=300)
    inside = fix(client, t, HOME, 120).json()
    assert inside["geofence_status"] == "inside" and inside["breach_started"] is False
    out = fix(client, t, FAR, 60).json()
    assert out["geofence_status"] == "outside" and out["breach_started"] is True
    ev = breaches(db, t["dep"], "open")
    assert len(ev) == 1 and ev[0].tier == "primary" and ev[0].resolved_at is None
    # staying outside does not raise a second alert
    again = fix(client, t, (LAT + 0.051, LNG), 30).json()
    assert again["geofence_status"] == "outside" and again["breach_started"] is False
    assert len(breaches(db, t["dep"])) == 1
    # back home closes it
    back = fix(client, t, HOME, 0).json()
    assert back["geofence_status"] == "inside"
    ev = breaches(db, t["dep"])
    assert len(ev) == 1 and ev[0].status == "resolved" and ev[0].resolved_at is not None
    # leaving again is a NEW breach
    out2 = fix(client, t, FAR, 0).json()
    assert out2["breach_started"] is True and len(breaches(db, t["dep"])) == 2


def test_multi_zone_breach_only_when_outside_all(client, db):
    t = team(client)
    add(client, t, name="Home", radius=300)
    add(client, t, name="Relative", lat=FAR[0], lng=FAR[1], radius=300)
    assert fix(client, t, HOME, 90).json()["geofence_status"] == "inside"
    moved = fix(client, t, FAR, 60).json()  # left home, but inside the relative's zone
    assert moved["geofence_status"] == "inside" and moved["breach_started"] is False
    assert breaches(db, t["dep"]) == []
    gone = fix(client, t, (LAT + 0.025, LNG), 0).json()  # between both
    assert gone["geofence_status"] == "outside" and gone["breach_started"] is True


def test_retrying_a_breach_fix_does_not_double_count(client, db):
    t = team(client)
    add(client, t)
    at = utcnow() - timedelta(seconds=20)
    first = send(client, t, lat=FAR[0], lng=FAR[1], at=at).json()
    retry = send(client, t, lat=FAR[0], lng=FAR[1], at=at).json()
    assert first["breach_started"] is True and retry["duplicate"] is True and retry["breach_started"] is False
    assert len(breaches(db, t["dep"])) == 1


def test_late_buffered_fix_cannot_change_the_state(client, db):
    t = team(client)
    add(client, t, radius=300)
    fix(client, t, HOME, 10)  # newest: inside
    late = fix(client, t, FAR, 600).json()  # an old fix from 10 minutes ago arrives late: it was outside
    assert late["breach_started"] is False
    assert breaches(db, t["dep"]) == []  # the newest fix says they are home, so no alert
    # reverse: they are outside now, an old "inside" fix arrives late
    fix(client, t, FAR, 0)
    assert len(breaches(db, t["dep"], "open")) == 1
    fix(client, t, HOME, 300)
    assert len(breaches(db, t["dep"], "open")) == 1  # still outside: not resolved by the stale fix


def test_gps_error_near_the_edge_is_not_a_breach(client, db):
    t = team(client)
    add(client, t, radius=200)
    just_out = (LAT + 0.0020, LNG)  # about 222 m
    r = fix(client, t, just_out, 0, accuracy_m=60).json()
    assert r["geofence_status"] == "inside" and r["breach_started"] is False
    assert breaches(db, t["dep"]) == []


# ------------------------------------------------------------ changing zones with a Dependent already outside

def test_adding_a_zone_away_from_the_dependent_opens_a_breach(client, db):
    t = team(client)
    fix(client, t, FAR, 0)  # no zones yet, no alert
    assert breaches(db, t["dep"]) == []
    add(client, t, radius=300)  # Home zone, but the Dependent is 5 km away
    assert len(breaches(db, t["dep"], "open")) == 1


def test_stale_position_never_opens_a_breach_from_a_zone_change(client, db):
    t = team(client)
    fix(client, t, FAR, 3 * 3600)  # last seen 3 hours ago
    add(client, t, radius=300)
    assert breaches(db, t["dep"]) == []  # we do not know where they are NOW


def test_widening_or_deleting_zones_resolves_the_breach(client, db):
    t = team(client)
    z = add(client, t, radius=200).json()
    fix(client, t, FAR, 0)
    assert len(breaches(db, t["dep"], "open")) == 1
    url = f"/dependents/{t['dep']}/geofences/{z['geofence_id']}"
    # move the zone onto the Dependent
    assert client.put(url, json=zone("Moved", FAR[0], FAR[1], 300), headers=auth(t["pt"])).status_code == 200
    assert breaches(db, t["dep"], "open") == [] and len(breaches(db, t["dep"], "resolved")) == 1
    # move it away again: new breach; deleting the only zone closes it
    client.put(url, json=zone("Home", LAT, LNG, 300), headers=auth(t["pt"]))
    assert len(breaches(db, t["dep"], "open")) == 1
    assert client.delete(url, headers=auth(t["pt"])).status_code == 204
    assert breaches(db, t["dep"], "open") == []


def test_geofence_status_endpoint(client):
    t = team(client)
    url = f"/dependents/{t['dep']}/geofence-status"
    assert client.get(url, headers=auth(t["pt"])).json()["status"] == "unknown"  # no fix yet
    z = add(client, t, radius=300).json()
    fix(client, t, HOME, 5)
    s = client.get(url, headers=auth(t["pt"])).json()
    assert s["status"] == "inside" and s["inside_zone_ids"] == [z["geofence_id"]] and s["breach_open"] is False
    fix(client, t, FAR, 0)
    s = client.get(url, headers=auth(t["pt"])).json()
    assert s["status"] == "outside" and s["breach_open"] is True and s["breach_since"] and s["breach_event_id"]


def test_old_fix_reads_as_unknown_status(client):
    t = team(client)
    add(client, t)
    fix(client, t, HOME, 2 * 3600)
    s = client.get(f"/dependents/{t['dep']}/geofence-status", headers=auth(t["pt"])).json()
    assert s["status"] == "unknown"


def test_breach_state_is_per_dependent(client, db):
    t = team(client)
    add(client, t)
    pt2, _, _ = make_guardian(client, 8)
    dep2 = make_dependent(client, 3)
    assert link(client, pt2, dep2).status_code == 201
    fix(client, t, FAR, 0)
    assert len(breaches(db, t["dep"], "open")) == 1 and breaches(db, dep2) == []


def test_simultaneous_exit_fixes_open_exactly_one_breach(client, db, engine, monkeypatch):
    """Two requests both see 'no open breach' at the same moment. Without the lock both would open one."""
    import uuid

    t = team(client)
    add(client, t, radius=300)
    barrier = threading.Barrier(2)
    original = geofence_service._open_event

    def paused(db_, dep, lock=False):
        ev = original(db_, dep, lock)
        if not lock:  # pause only on the unlocked first look
            try:
                barrier.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
        return ev

    monkeypatch.setattr(geofence_service, "_open_event", paused)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def attempt(_):
        s = Session()
        try:
            return geofence_service.sync_breach_state(s, uuid.UUID(t["dep"]), "outside") and (s.commit() or True)
        finally:
            s.close()

    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(attempt, range(2)))
    assert len(breaches(db, t["dep"], "open")) == 1, results
    assert sum(1 for r in results if r) == 1
