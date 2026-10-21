"""
Task 6.3 tests: camera pairing, on-demand viewing and permission gating (FR-K1).
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, CameraDevice, CameraSession
from app.services import camera_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_permissions import put


def pair(client, token, dep, **body):
    return client.post(f"/dependents/{dep}/camera", json=body, headers=auth(token))


def beat(client, token, dep):
    return client.post(f"/dependents/{dep}/camera/heartbeat", headers=auth(token))


def watch(client, token, dep):
    return client.get(f"/dependents/{dep}/camera/stream", headers=auth(token))


def leave(client, token, dep):
    return client.delete(f"/dependents/{dep}/camera/stream", headers=auth(token))


def viewing(client, token, dep):
    return client.get(f"/dependents/{dep}/camera/viewing", headers=auth(token))


def allow_cam(client, t, granted=True):
    assert put(client, t["pt"], t["dep"], "camera_viewing", t["sid"], granted).status_code == 200


def ready(client):
    """A team with a paired camera that is online."""
    t = team(client)
    assert pair(client, t["dt"], t["dep"], name="Hall phone").status_code == 201
    assert beat(client, t["dt"], t["dep"]).status_code == 200
    return t


def get_status(client, token, dep):
    r = client.get(f"/dependents/{dep}/camera", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------ pairing

def test_pair_by_dependent_and_repeat_updates(client, db):
    t = team(client)
    assert get_status(client, t["pt"], t["dep"])["paired"] is False
    r = pair(client, t["dt"], t["dep"], name="Hall phone")
    assert r.status_code == 201 and r.json()["paired"] and r.json()["name"] == "Hall phone" and r.json()["online"] is False
    r2 = pair(client, t["pt"], t["dep"], name="Kitchen")
    assert r2.status_code == 200 and r2.json()["name"] == "Kitchen"
    assert r2.json()["camera_id"] == r.json()["camera_id"]
    assert db.scalar(select(func.count()).select_from(CameraDevice)) == 1


def test_pair_rules(client):
    t = team(client)
    assert_error(pair(client, t["st"], t["dep"]), 403, "FORBIDDEN")  # a Secondary cannot pair
    assert pair(client, t["dt"], t["dep"], name="   ").json()["name"] is None  # blank means no label
    assert pair(client, t["dt"], t["dep"], name="x" * 61).status_code == 422
    assert client.post(f"/dependents/{t['dep']}/camera", json={}).status_code == 401


def test_unpair_ends_sessions_and_is_idempotent(client, db):
    t = ready(client)
    assert watch(client, t["pt"], t["dep"]).status_code == 200
    assert client.delete(f"/dependents/{t['dep']}/camera", headers=auth(t["st"])).status_code == 403
    assert client.delete(f"/dependents/{t['dep']}/camera", headers=auth(t["pt"])).status_code == 204
    assert client.delete(f"/dependents/{t['dep']}/camera", headers=auth(t["pt"])).status_code == 204
    assert get_status(client, t["pt"], t["dep"])["paired"] is False
    db.expire_all()
    assert db.scalar(select(CameraSession.end_reason)) == "unpaired"
    assert_error(watch(client, t["pt"], t["dep"]), 409, "NO_CAMERA")


def test_status_visibility(client):
    t = ready(client)
    assert get_status(client, t["dt"], t["dep"])["paired"]
    assert_error(client.get(f"/dependents/{t['dep']}/camera", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    allow_cam(client, t)
    assert get_status(client, t["st"], t["dep"])["online"] is True


# ------------------------------------------------------------ the camera phone

def test_heartbeat_idle_then_publish_while_viewed(client):
    t = ready(client)
    h = beat(client, t["dt"], t["dep"]).json()
    assert h["should_publish"] is False and h["next_poll_s"] == 10 and h["join"] is None
    assert watch(client, t["pt"], t["dep"]).status_code == 200
    h = beat(client, t["dt"], t["dep"]).json()
    assert h["should_publish"] is True and h["viewers_now"] == 1 and h["next_poll_s"] == 5
    assert h["join"]["token"].startswith("mock-pub-") and h["join"]["user_id"] == f"camera-{t['dep']}"
    assert leave(client, t["pt"], t["dep"]).status_code == 204
    assert beat(client, t["dt"], t["dep"]).json()["should_publish"] is False


def test_heartbeat_only_for_the_dependent_and_needs_camera(client):
    t = team(client)
    assert_error(beat(client, t["dt"], t["dep"]), 409, "NO_CAMERA")
    pair(client, t["dt"], t["dep"])
    assert_error(beat(client, t["pt"], t["dep"]), 403, "FORBIDDEN")
    assert_error(beat(client, t["st"], t["dep"]), 403, "FORBIDDEN")


# ------------------------------------------------------------ viewing and the gate

def test_primary_views_and_token_cannot_publish(client):
    t = ready(client)
    r = watch(client, t["pt"], t["dep"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["renewed"] is False and b["join"]["token"].startswith("mock-view-") and b["join"]["room_id"] == f"cam-{uuid.UUID(t['dep']).hex}"
    assert b["join"]["stream_id"] == b["join"]["room_id"] + "-stream" and b["renew_every_s"] == 30
    assert r.headers["cache-control"] == "private, no-store"
    r2 = watch(client, t["pt"], t["dep"])
    assert r2.json()["renewed"] is True and r2.json()["session_id"] == b["session_id"]
    assert r2.json()["expires_at"] >= b["expires_at"]


def test_secondary_needs_camera_viewing(client):
    t = ready(client)
    assert_error(watch(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    allow_cam(client, t)
    assert watch(client, t["st"], t["dep"]).status_code == 200
    # Secondary joins under its own user id
    assert watch(client, t["st"], t["dep"]).json()["join"]["user_id"] == t["sid"]


def test_dependent_and_strangers_cannot_view(client):
    t = ready(client)
    assert_error(watch(client, t["dt"], t["dep"]), 403, "FORBIDDEN")
    other = team_other(client)
    assert watch(client, other, t["dep"]).status_code in (403,)
    assert client.get(f"/dependents/{t['dep']}/camera/stream").status_code == 401


def team_other(client):
    from tests.test_linkage import make_guardian
    tok, _, _ = make_guardian(client, 7)
    return tok


def test_offline_camera(client, db):
    t = ready(client)
    db.query(CameraDevice).update({"last_seen_at": datetime.now(timezone.utc) - timedelta(seconds=60)})
    db.commit()
    assert_error(watch(client, t["pt"], t["dep"]), 409, "CAMERA_OFFLINE")
    assert get_status(client, t["pt"], t["dep"])["online"] is False
    pair(client, t["dt"], t["dep"])
    db.query(CameraDevice).update({"last_seen_at": None})
    db.commit()
    assert_error(watch(client, t["pt"], t["dep"]), 409, "CAMERA_OFFLINE")


def test_viewer_limit_blocks_new_viewer(client, db, monkeypatch):
    t = ready(client)
    allow_cam(client, t)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "CAMERA_MAX_VIEWERS", 1)
    assert watch(client, t["pt"], t["dep"]).status_code == 200
    assert_error(watch(client, t["st"], t["dep"]), 409, "TOO_MANY_VIEWERS")
    assert watch(client, t["pt"], t["dep"]).json()["renewed"] is True  # the one inside can still renew
    assert leave(client, t["pt"], t["dep"]).status_code == 204
    assert watch(client, t["st"], t["dep"]).status_code == 200


def test_permission_revoked_closes_session(client, db):
    t = ready(client)
    allow_cam(client, t)
    assert watch(client, t["st"], t["dep"]).status_code == 200
    assert viewing(client, t["dt"], t["dep"]).json()["being_viewed"] is True
    allow_cam(client, t, False)
    assert_error(watch(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    v = viewing(client, t["dt"], t["dep"]).json()
    assert v["being_viewed"] is False and v["viewers"] == []
    assert beat(client, t["dt"], t["dep"]).json()["should_publish"] is False
    db.expire_all()
    assert db.scalar(select(CameraSession.end_reason)) == "permission_revoked"


def test_expired_session_is_closed(client, db):
    t = ready(client)
    assert watch(client, t["pt"], t["dep"]).status_code == 200
    db.query(CameraSession).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1), "started_at": datetime.now(timezone.utc) - timedelta(seconds=100)})
    db.commit()
    assert viewing(client, t["dt"], t["dep"]).json()["being_viewed"] is False
    db.expire_all()
    assert db.scalar(select(CameraSession.end_reason)) == "expired"
    r = watch(client, t["pt"], t["dep"])  # a new one can start
    assert r.status_code == 200 and r.json()["renewed"] is False


def test_sweep_job(client, db):
    t = ready(client)
    allow_cam(client, t)
    watch(client, t["pt"], t["dep"])
    watch(client, t["st"], t["dep"])
    allow_cam(client, t, False)
    assert camera_service.sweep(db) == 1
    assert camera_service.sweep(db) == 0
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CameraSession).where(CameraSession.ended_at.is_(None))) == 1


# ------------------------------------------------------------ indicator, notices, audit

def test_viewing_indicator_names_and_roles(client):
    t = ready(client)
    allow_cam(client, t)
    assert viewing(client, t["dt"], t["dep"]).json() == {"being_viewed": False, "viewers": []}
    watch(client, t["pt"], t["dep"])
    watch(client, t["st"], t["dep"])
    v = viewing(client, t["dt"], t["dep"]).json()
    assert v["being_viewed"] is True and {x["role"] for x in v["viewers"]} == {"primary", "secondary"}
    assert all(x["full_name"] for x in v["viewers"])
    assert_error(viewing(client, t["pt"], t["dep"]), 403, "FORBIDDEN")
    assert viewing(client, t["dt"], t["dep"]).headers["cache-control"] == "private, no-store"


def test_notifications_on_new_session_only(client):
    t = ready(client)
    allow_cam(client, t)
    watch(client, t["st"], t["dep"])
    watch(client, t["st"], t["dep"])  # renew: no second notice
    d = [n for n in inbox(client, t["dt"])["items"] if n["type"] == "camera_view"]
    p = [n for n in inbox(client, t["pt"])["items"] if n["type"] == "camera_view"]
    assert len(d) == 1 and len(p) == 1  # the Dependent and the Primary (a Secondary watched)
    assert not [n for n in inbox(client, t["st"])["items"] if n["type"] == "camera_view"]
    watch(client, t["pt"], t["dep"])  # the Primary watching: Dependent told, Primary not told about itself
    assert len([n for n in inbox(client, t["dt"])["items"] if n["type"] == "camera_view"]) == 2
    assert len([n for n in inbox(client, t["pt"])["items"] if n["type"] == "camera_view"]) == 1


def test_audit_rows(client, db):
    t = ready(client)
    watch(client, t["pt"], t["dep"])
    leave(client, t["pt"], t["dep"])
    client.delete(f"/dependents/{t['dep']}/camera", headers=auth(t["pt"]))
    actions = [a for a in db.scalars(select(AuditLog.action).order_by(AuditLog.occurred_at)).all() if a.startswith("camera_")]
    assert actions == ["camera_paired", "camera_view_started", "camera_view_ended", "camera_unpaired"]


# ------------------------------------------------------------ provider outage, DB rules, races

def test_provider_down_gives_503_and_no_session(client, db, monkeypatch):
    t = ready(client)
    monkeypatch.setattr("app.services.call_provider.room_token", lambda *a, **k: None)
    assert_error(watch(client, t["pt"], t["dep"]), 503, "STREAM_PROVIDER_UNAVAILABLE")
    assert db.scalar(select(func.count()).select_from(CameraSession)) == 0


def test_db_rules(client, db):
    t = ready(client)
    dep = uuid.UUID(t["dep"])
    now = datetime.now(timezone.utc)
    db.add(CameraDevice(dependent_id=dep, stream_uri="rtc:x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    viewer = db.scalar(select(AuditLog.actor_id))
    for kw in ({"expires_at": now - timedelta(seconds=5)}, {"ended_at": now}, {"end_reason": "stopped"}, {"ended_at": now, "end_reason": "bogus"}):
        base = dict(dependent_id=dep, viewer_id=viewer, started_at=now, last_renewed_at=now, expires_at=now + timedelta(seconds=9))
        base.update(kw)
        db.add(CameraSession(**base))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_parallel_starts_make_one_session(client, db):
    t = ready(client)
    n = 4
    barrier = Barrier(n)
    tok, dep = t["pt"], t["dep"]

    def go(_):
        barrier.wait()
        return watch(client, tok, dep).status_code

    with ThreadPoolExecutor(n) as ex:
        codes = list(ex.map(go, range(n)))
    assert set(codes) <= {200, 409}, codes
    assert 200 in codes
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CameraSession).where(CameraSession.ended_at.is_(None))) == 1
