"""
Task 6.6 tests: audit trail per Dependent, readable by the Primary Guardian only (FR-N3).
"""

import ast
import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.models import AuditLog
from tests.test_camera import allow_cam, beat, leave, pair, watch
from tests.test_linkage import PASSWORD, PHOTO, assert_error, auth, link, login, make_dependent, make_guardian
from tests.test_location import team
from tests.test_permissions import put

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def log(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/audit-log", params=params, headers=auth(token))


def busy_team(client):
    """A team where the Primary, the Dependent and the Secondary each did something worth logging."""
    t = team(client)
    allow_cam(client, t)  # permission_granted (Primary)
    assert pair(client, t["dt"], t["dep"], name="Hall phone").status_code == 201  # camera_paired (Dependent)
    assert beat(client, t["dt"], t["dep"]).status_code == 200
    assert watch(client, t["st"], t["dep"]).status_code == 200  # camera_view_started (Secondary)
    assert leave(client, t["st"], t["dep"]).status_code in (200, 204)  # camera_view_ended
    return t


# ------------------------------------------------------------ structure

def test_every_audit_write_names_the_dependent():
    """Static guard: no `AuditLog(...)` anywhere in app/ is built without dependent_id."""
    bad = []
    for path in APP.rglob("*.py"):
        if path.name == "security.py" and path.parent.name == "models":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "AuditLog":
                if "dependent_id" not in {k.arg for k in node.keywords}:
                    bad.append(f"{path.name}:{node.lineno}")
    assert bad == []


# ------------------------------------------------------------ reading

def test_primary_reads_the_history_newest_first(client, db):
    t = busy_team(client)
    r = log(client, t["pt"], t["dep"])
    assert r.status_code == 200, r.text
    body = r.json()
    actions = [e["action"] for e in body["items"]]
    assert actions[:4] == ["camera_view_ended", "camera_view_started", "camera_paired", "permission_granted"]
    assert body["total"] == len(body["items"]) >= 4
    times = [e["occurred_at"] for e in body["items"]]
    assert times == sorted(times, reverse=True)
    started = next(e for e in body["items"] if e["action"] == "camera_view_started")
    assert started["label"] == "Started watching the camera"
    assert started["actor"]["user_id"] == t["sid"] and started["actor"]["role"] == "guardian" and started["actor"]["full_name"]
    paired = next(e for e in body["items"] if e["action"] == "camera_paired")
    assert paired["actor"]["user_id"] == t["dep"] and paired["actor"]["role"] == "dependent"


def test_only_the_primary_can_read(client):
    t = busy_team(client)
    assert_error(log(client, t["st"], t["dep"]), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(log(client, t["dt"], t["dep"]), 403, "FORBIDDEN")
    assert client.get(f"/dependents/{t['dep']}/audit-log").status_code == 401


def test_a_guardian_not_linked_gets_nothing(client):
    t = team(client)
    token, _, _ = make_guardian(client, 7)
    assert_error(log(client, token, t["dep"]), 403, "NOT_LINKED_TO_DEPENDENT")


def test_each_dependent_has_their_own_history(client):
    t = busy_team(client)
    dep2 = make_dependent(client, 2)
    k = client.post(f"/dependents/{dep2}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-7654322-1", "liveness_image": PHOTO})
    assert k.json()["status"] == "verified"
    assert link(client, t["pt"], dep2).status_code == 201
    dt2, _ = login(client, "d2@link-test.com")
    assert pair(client, dt2, dep2, name="Bedroom").status_code == 201
    one = log(client, t["pt"], t["dep"]).json()["items"]
    two = log(client, t["pt"], dep2).json()
    assert [e["action"] for e in two["items"]] == ["camera_paired"]
    assert all(e["audit_id"] not in {x["audit_id"] for x in one} for e in two["items"])
    assert "Bedroom" not in str(one)


def test_filters(client):
    t = busy_team(client)
    only = log(client, t["pt"], t["dep"], action="camera_paired").json()
    assert [e["action"] for e in only["items"]] == ["camera_paired"] and only["total"] == 1
    by_sec = log(client, t["pt"], t["dep"], actor_id=t["sid"]).json()
    assert {e["actor"]["user_id"] for e in by_sec["items"]} == {t["sid"]} and by_sec["total"] == 2
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert log(client, t["pt"], t["dep"], since=future).json()["total"] == 0
    assert log(client, t["pt"], t["dep"], until=past).json()["total"] == 0
    assert log(client, t["pt"], t["dep"], since=past, until=future).json()["total"] >= 4


def test_paging(client):
    t = busy_team(client)
    full = log(client, t["pt"], t["dep"]).json()
    first = log(client, t["pt"], t["dep"], limit=2).json()
    second = log(client, t["pt"], t["dep"], limit=2, offset=2).json()
    assert [e["audit_id"] for e in first["items"] + second["items"]] == [e["audit_id"] for e in full["items"][:4]]
    assert first["total"] == full["total"] and first["limit"] == 2 and second["offset"] == 2
    assert log(client, t["pt"], t["dep"], limit=0).status_code == 422
    assert log(client, t["pt"], t["dep"], limit=101).status_code == 422
    assert log(client, t["pt"], t["dep"], offset=-1).status_code == 422


def test_the_log_cannot_be_changed_through_the_api(client):
    t = busy_team(client)
    for method in ("post", "put", "patch", "delete"):
        r = getattr(client, method)(f"/dependents/{t['dep']}/audit-log", headers=auth(t["pt"]))
        assert r.status_code == 405, method


def test_unknown_action_still_gets_a_readable_label(client, db):
    t = team(client)
    db.add(AuditLog(actor_id=t["sid"], action="some_new_thing", target_type="dependent", target_id=t["dep"], dependent_id=t["dep"]))
    db.commit()
    e = log(client, t["pt"], t["dep"]).json()["items"][0]
    assert e["label"] == "Some new thing"


# ------------------------------------------------------------ migration backfill

def test_migration_backfill_finds_the_dependent_for_old_rows(client, db):
    t = busy_team(client)
    before = {r.audit_id: r.dependent_id for r in db.scalars(select(AuditLog)).all()}
    assert before and all(v == __import__("uuid").UUID(t["dep"]) for v in before.values())
    db.execute(text("UPDATE audit_logs SET dependent_id = NULL"))
    db.commit()
    path = next((APP.parent / "alembic" / "versions").glob("*0020_audit_log_dependent*.py"))
    spec = importlib.util.spec_from_file_location("mig0020", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for _name, sql in mod.BACKFILL:
        db.execute(text(sql))
    db.commit()
    db.expire_all()
    after = {r.audit_id: r.dependent_id for r in db.scalars(select(AuditLog)).all()}
    assert after == before
