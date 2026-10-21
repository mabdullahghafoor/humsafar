"""
Task 6.4 tests: event-triggered clip capture (FR-K2).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models import AuditLog, CameraClip
from app.services import camera_clip_service as cs
from tests.test_alarm import start as sound_alarm
from tests.test_camera import allow_cam, beat, pair
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_panic import press, push  # noqa: F401 (push is a fixture)

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 100


@pytest.fixture(autouse=True)
def clip_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "CLIPS_STORAGE_DIR", str(tmp_path / "clips"))


def up(client, token, dep, clip_id, data=MP4, name="c.mp4"):
    return client.post(f"/dependents/{dep}/camera/clips/{clip_id}", files={"file": (name, data, "video/mp4")}, headers=auth(token))


def clips(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/camera/clips", params=params, headers=auth(token))


def ready(client):
    t = team(client)
    assert pair(client, t["dt"], t["dep"]).status_code == 201
    return t


def pending(client, t):
    r = beat(client, t["dt"], t["dep"])
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------ requests

def test_panic_with_camera_asks_the_phone_to_record(client, db, push):
    t = ready(client)
    assert press(client, t).status_code == 201
    h = pending(client, t)
    c = h["clip"]
    assert c and c["trigger_type"] == "panic" and c["duration_s"] == 20 and h["next_poll_s"] == 5 and h["should_publish"] is False
    assert pending(client, t)["clip"]["clip_id"] == c["clip_id"]  # still waiting until uploaded
    row = db.scalar(select(CameraClip))
    assert row.status == "requested" and row.event_id is not None


def test_alarm_also_asks(client, db, push):
    t = ready(client)
    assert sound_alarm(client, t).status_code == 201
    assert pending(client, t)["clip"]["trigger_type"] == "remote_alarm"


def test_no_camera_no_request_and_emergency_unaffected(client, db, push):
    t = team(client)
    assert press(client, t).status_code == 201
    assert db.scalar(select(func.count()).select_from(CameraClip)) == 0


def test_second_press_makes_no_second_request(client, db, push):
    t = ready(client)
    press(client, t)
    press(client, t)
    assert db.scalar(select(func.count()).select_from(CameraClip)) == 1


def test_storage_cap_stops_new_requests(client, db, push, monkeypatch):
    t = ready(client)
    monkeypatch.setattr(get_settings(), "CLIPS_MAX_PER_DEPENDENT", 0)
    assert press(client, t).status_code == 201  # the emergency still works
    assert db.scalar(select(func.count()).select_from(CameraClip)) == 0


def test_a_failing_clip_request_never_breaks_panic(client, db, push, monkeypatch):
    t = ready(client)
    monkeypatch.setattr(cs, "CameraClip", None)
    assert press(client, t).status_code == 201


# ------------------------------------------------------------ upload

def test_upload_stores_encrypted_and_tells_the_family(client, db, push):
    t = ready(client)
    allow_cam(client, t)
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    r = up(client, t["dt"], t["dep"], cid)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "stored" and j["size_bytes"] == len(MP4) and j["content_type"] == "video/mp4" and j["uploaded_at"]
    row = db.scalar(select(CameraClip))
    stored = (get_settings().CLIPS_STORAGE_DIR and __import__("pathlib").Path(get_settings().CLIPS_STORAGE_DIR) / row.file_url).read_bytes()
    assert MP4 not in stored and stored[:3] == b"HV1"  # encrypted at rest (FR-N2)
    assert pending(client, t)["clip"] is None and pending(client, t)["next_poll_s"] == 10
    for tok in (t["pt"], t["st"]):
        assert len([n for n in inbox(client, tok)["items"] if n["type"] == "camera_clip"]) == 1
    assert not [n for n in inbox(client, t["dt"])["items"] if n["type"] == "camera_clip"]


def test_secondary_without_camera_viewing_gets_no_notice(client, push):
    t = ready(client)
    press(client, t)
    up(client, t["dt"], t["dep"], pending(client, t)["clip"]["clip_id"])
    assert len([n for n in inbox(client, t["pt"])["items"] if n["type"] == "camera_clip"]) == 1
    assert not [n for n in inbox(client, t["st"])["items"] if n["type"] == "camera_clip"]


def test_webm_accepted_and_bad_files_refused(client, db, push, monkeypatch):
    t = ready(client)
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    assert_error(up(client, t["dt"], t["dep"], cid, b"hello this is not a video"), 415, "UNSUPPORTED_FILE")
    assert_error(up(client, t["dt"], t["dep"], cid, b""), 415, "UNSUPPORTED_FILE")
    monkeypatch.setattr(get_settings(), "CLIP_MAX_BYTES", 150)
    assert_error(up(client, t["dt"], t["dep"], cid, MP4), 413, "FILE_TOO_LARGE")
    monkeypatch.setattr(get_settings(), "CLIP_MAX_BYTES", 30_000_000)
    assert up(client, t["dt"], t["dep"], cid, WEBM, "c.webm").json()["content_type"] == "video/webm"
    assert db.scalar(select(func.count()).select_from(CameraClip).where(CameraClip.status == "stored")) == 1


def test_upload_rules(client, db, push):
    t = ready(client)
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    assert_error(up(client, t["pt"], t["dep"], cid), 403, "FORBIDDEN")
    assert_error(up(client, t["dt"], t["dep"], str(uuid.uuid4())), 404, "CLIP_NOT_FOUND")
    assert up(client, t["dt"], t["dep"], cid).status_code == 201
    assert_error(up(client, t["dt"], t["dep"], cid), 409, "CLIP_ALREADY_STORED")
    assert client.post(f"/dependents/{t['dep']}/camera/clips/{cid}", files={"file": ("c.mp4", MP4)}).status_code == 401


def test_late_upload_is_refused_and_marked_missed(client, db, push):
    t = ready(client)
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    db.query(CameraClip).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    db.commit()
    assert_error(up(client, t["dt"], t["dep"], cid), 409, "CLIP_EXPIRED")
    db.expire_all()
    assert db.scalar(select(CameraClip.status)) == "missed"
    assert pending(client, t)["clip"] is None
    import pathlib
    d = pathlib.Path(get_settings().CLIPS_STORAGE_DIR)
    assert not d.exists() or not list(d.iterdir())  # the refused file is not kept


def test_sweep_marks_missed_and_unpair_too(client, db, push):
    t = ready(client)
    press(client, t)
    db.query(CameraClip).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    db.commit()
    assert cs.sweep(db) == 1 and cs.sweep(db) == 0
    db.expire_all()
    assert db.scalar(select(CameraClip.status)) == "missed"
    sound_alarm(client, t)
    assert db.scalar(select(func.count()).select_from(CameraClip).where(CameraClip.status == "requested")) == 1
    assert client.delete(f"/dependents/{t['dep']}/camera", headers=auth(t["pt"])).status_code == 204
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CameraClip).where(CameraClip.status == "requested")) == 0


# ------------------------------------------------------------ reading

def stored(client, t):
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    assert up(client, t["dt"], t["dep"], cid).status_code == 201
    return cid


def test_list_and_gate(client, db, push):
    t = ready(client)
    cid = stored(client, t)
    for tok in (t["pt"], t["dt"]):
        j = clips(client, tok, t["dep"]).json()
        assert j["total"] == 1 and j["items"][0]["clip_id"] == cid and j["items"][0]["trigger_type"] == "panic"
    assert_error(clips(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    allow_cam(client, t)
    assert clips(client, t["st"], t["dep"]).json()["total"] == 1
    assert clips(client, t["pt"], t["dep"], status="missed").json()["total"] == 0
    assert clips(client, t["pt"], t["dep"], status="weird").status_code == 422
    assert clips(client, t["pt"], t["dep"]).headers["cache-control"] == "private, no-store"
    assert client.get(f"/dependents/{t['dep']}/camera/clips/{cid}", headers=auth(t["pt"])).json()["status"] == "stored"


def test_download_decrypts_and_is_audited_for_guardians(client, db, push):
    t = ready(client)
    cid = stored(client, t)
    url = f"/dependents/{t['dep']}/camera/clips/{cid}/video"
    r = client.get(url, headers=auth(t["pt"]))
    assert r.status_code == 200 and r.content == MP4 and r.headers["content-type"] == "video/mp4" and "attachment" in r.headers["content-disposition"]
    assert client.get(url, headers=auth(t["dt"])).content == MP4  # the Dependent's own clip
    assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    n = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "camera_clip_viewed"))
    assert n == 1  # only the Guardian's download
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "camera_clip_stored")) == 1


def test_download_of_a_request_without_video(client, db, push):
    t = ready(client)
    press(client, t)
    cid = pending(client, t)["clip"]["clip_id"]
    assert_error(client.get(f"/dependents/{t['dep']}/camera/clips/{cid}/video", headers=auth(t["pt"])), 404, "CLIP_NOT_FOUND")


def test_tampered_file_is_refused(client, db, push):
    import pathlib
    t = ready(client)
    cid = stored(client, t)
    row = db.scalar(select(CameraClip))
    p = pathlib.Path(get_settings().CLIPS_STORAGE_DIR) / row.file_url
    b = bytearray(p.read_bytes()); b[-1] ^= 1; p.write_bytes(bytes(b))
    assert_error(client.get(f"/dependents/{t['dep']}/camera/clips/{cid}/video", headers=auth(t["pt"])), 500, "CLIP_UNREADABLE")


def test_delete_rules(client, db, push):
    import pathlib
    t = ready(client)
    allow_cam(client, t)
    cid = stored(client, t)
    base = f"/dependents/{t['dep']}/camera/clips/{cid}"
    assert_error(client.delete(base, headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert client.delete(base, headers=auth(t["pt"])).status_code == 204
    assert client.delete(base, headers=auth(t["pt"])).status_code == 204  # safe to repeat
    assert_error(client.get(base, headers=auth(t["pt"])), 404, "CLIP_NOT_FOUND")
    assert not list(pathlib.Path(get_settings().CLIPS_STORAGE_DIR).iterdir())
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "camera_clip_deleted")) == 1


def test_dependent_can_delete_own_clip(client, db, push):
    t = ready(client)
    cid = stored(client, t)
    assert client.delete(f"/dependents/{t['dep']}/camera/clips/{cid}", headers=auth(t["dt"])).status_code == 204


def test_db_rules(client, db, push):
    t = ready(client)
    dep = uuid.UUID(t["dep"])
    ev = uuid.uuid4()
    for kw in ({"trigger_type": "bogus"}, {"status": "bogus"}, {"status": "stored"}, {"status": "requested", "file_url": "x"}, {"size_bytes": 0}):
        base = dict(dependent_id=dep, trigger_type="panic", status="requested")
        base.update(kw)
        db.add(CameraClip(**base))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    db.add(CameraClip(dependent_id=dep, trigger_type="panic", event_id=ev)); db.commit()
    db.add(CameraClip(dependent_id=dep, trigger_type="panic", event_id=ev))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
