"""
Task 1.6 tests: permission dashboard (FR-A4) and the module access gate.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.core.deps import require_module_access
from app.core.errors import AppError
from app.main import app
from app.models import AuditLog, PermissionGrant, User
from app.models.identity import PERMISSION_MODULES
from app.services import permission_service
from tests.test_linkage import (
    assert_error,
    auth,
    invite,
    link,
    login,
    make_dependent,
    make_guardian,
    make_secondary,
    register,
)


def verify(client, token):
    r = client.post("/guardians/me/verify-cnic", json={"cnic": "42101-1234567-1"}, headers=auth(token))
    assert r.json()["verified"] is True


def team(client):
    """Primary linked to a Dependent, plus one Secondary. Returns a dict of tokens and ids."""
    pt, pid, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    assert link(client, pt, dep).status_code == 201
    st, sid, _ = make_secondary(client, pt, dep, 1)
    verify(client, st)
    return {"pt": pt, "pid": pid, "dep": dep, "st": st, "sid": sid}


def put(client, token, dep, module, guardian_id, granted):
    return client.put(
        f"/dependents/{dep}/permissions/{module}",
        json={"guardian_id": guardian_id, "granted": granted},
        headers=auth(token),
    )


def mine(client, token, dep):
    return client.get(f"/dependents/{dep}/permissions/me", headers=auth(token))


# ------------------------------------------------------------ defaults

def test_default_deny_for_a_new_secondary(client):
    t = team(client)
    dash = client.get(f"/dependents/{t['dep']}/permissions", headers=auth(t["pt"]))
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["modules"] == list(PERMISSION_MODULES)
    assert len(body["secondaries"]) == 1
    assert body["secondaries"][0]["guardian_id"] == t["sid"]
    assert body["secondaries"][0]["modules"] == {m: False for m in PERMISSION_MODULES}
    own = mine(client, t["st"], t["dep"]).json()
    assert own["guardian_role"] == "secondary" and not any(own["modules"].values())


def test_primary_has_every_module_and_remote_alarm_is_not_a_module(client):
    t = team(client)
    own = mine(client, t["pt"], t["dep"]).json()
    assert own["guardian_role"] == "primary"
    assert own["modules"] == {m: True for m in PERMISSION_MODULES}
    assert not any("alarm" in m for m in PERMISSION_MODULES)


# ------------------------------------------------------ grant and revoke

def test_grant_and_revoke_one_module_independently(client):
    t = team(client)
    r = put(client, t["pt"], t["dep"], "live_location", t["sid"], True)
    assert r.status_code == 200, r.text
    assert r.json()["granted"] is True and r.json()["module"] == "live_location"
    assert put(client, t["pt"], t["dep"], "camera_viewing", t["sid"], True).status_code == 200

    own = mine(client, t["st"], t["dep"]).json()["modules"]
    assert own["live_location"] is True and own["camera_viewing"] is True
    assert own["health_records"] is False

    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], False).json()["granted"] is False
    own = mine(client, t["st"], t["dep"]).json()["modules"]
    assert own["live_location"] is False and own["camera_viewing"] is True  # only the one changed


def test_granting_twice_is_harmless(client):
    t = team(client)
    for _ in range(2):
        r = put(client, t["pt"], t["dep"], "communication", t["sid"], True)
        assert r.status_code == 200 and r.json()["granted"] is True


def test_every_governable_module_can_be_granted(client):
    t = team(client)
    for m in PERMISSION_MODULES:
        assert put(client, t["pt"], t["dep"], m, t["sid"], True).status_code == 200
    assert all(mine(client, t["st"], t["dep"]).json()["modules"].values())


# ----------------------------------------- the gate: revoke is immediate

def test_revoking_blocks_the_secondary_on_the_next_call(client):
    path = "/__test__/{dependent_id}/location"

    def _probe(dependent_id: uuid.UUID, user: User = Depends(require_module_access("live_location"))):
        return {"ok": True}

    app.add_api_route(path, _probe, methods=["GET"])
    try:
        t = team(client)
        url = f"/__test__/{t['dep']}/location"
        assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")  # default deny
        put(client, t["pt"], t["dep"], "live_location", t["sid"], True)
        assert client.get(url, headers=auth(t["st"])).json() == {"ok": True}
        put(client, t["pt"], t["dep"], "live_location", t["sid"], False)
        assert_error(client.get(url, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")  # same token, next call
        assert client.get(url, headers=auth(t["pt"])).json() == {"ok": True}  # Primary always passes
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]


def test_unverified_secondary_is_blocked_even_when_granted(client):
    path = "/__test__/{dependent_id}/camera"

    def _probe(dependent_id: uuid.UUID, user: User = Depends(require_module_access("camera_viewing"))):
        return {"ok": True}

    app.add_api_route(path, _probe, methods=["GET"])
    try:
        pt, _, _ = make_guardian(client, 1)
        dep = make_dependent(client, 1)
        link(client, pt, dep)
        st, sid, _ = make_secondary(client, pt, dep, 1)  # NOT verified
        assert put(client, pt, dep, "camera_viewing", sid, True).status_code == 200
        assert_error(client.get(f"/__test__/{dep}/camera", headers=auth(st)), 403, "GUARDIAN_NOT_VERIFIED")
        verify(client, st)
        assert client.get(f"/__test__/{dep}/camera", headers=auth(st)).json() == {"ok": True}
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]


def test_gate_rejects_unlinked_guardians_dependents_and_anonymous(client):
    path = "/__test__/{dependent_id}/records"

    def _probe(dependent_id: uuid.UUID, user: User = Depends(require_module_access("health_records"))):
        return {"ok": True}

    app.add_api_route(path, _probe, methods=["GET"])
    try:
        t = team(client)
        url = f"/__test__/{t['dep']}/records"
        other, _, _ = make_guardian(client, 2)
        assert_error(client.get(url, headers=auth(other)), 403, "NOT_LINKED_TO_DEPENDENT")
        dep_token = security.create_access_token(uuid.UUID(t["dep"]), "dependent")
        assert_error(client.get(url, headers=auth(dep_token)), 403, "FORBIDDEN")
        assert_error(client.get(url), 401, "NOT_AUTHENTICATED")
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]


# ---------------------------------------------------- who may change what

def test_secondary_cannot_change_permissions(client):
    t = team(client)
    assert_error(put(client, t["st"], t["dep"], "live_location", t["sid"], True), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.get(f"/dependents/{t['dep']}/permissions", headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")


def test_another_dependents_primary_cannot_change_permissions(client):
    t = team(client)
    other, _, _ = make_guardian(client, 2)
    dep2 = make_dependent(client, 2)
    assert link(client, other, dep2).status_code == 201
    assert_error(put(client, other, t["dep"], "live_location", t["sid"], True), 403, "NOT_PRIMARY_GUARDIAN")


def test_unverified_or_anonymous_callers_are_rejected(client):
    t = team(client)
    unverified, uid, _ = make_guardian(client, 3, verified=False)
    assert_error(put(client, unverified, t["dep"], "live_location", t["sid"], True), 403, "GUARDIAN_NOT_VERIFIED")
    r = client.put(f"/dependents/{t['dep']}/permissions/live_location", json={"guardian_id": t["sid"], "granted": True})
    assert_error(r, 401, "NOT_AUTHENTICATED")


def test_unknown_dependent_looks_like_not_primary(client):
    t = team(client)
    assert_error(put(client, t["pt"], str(uuid.uuid4()), "live_location", t["sid"], True), 403, "NOT_PRIMARY_GUARDIAN")


# -------------------------------------------------------------- validation

def test_unknown_module_and_remote_alarm_are_rejected(client):
    t = team(client)
    for bad in ["remote_alarm", "remote_alarm_override", "nonsense", "LIVE_LOCATION"]:
        r = put(client, t["pt"], t["dep"], bad, t["sid"], True)
        assert_error(r, 422, "UNKNOWN_MODULE")
        assert r.json()["error"]["details"]["allowed"] == list(PERMISSION_MODULES)


def test_body_validation(client):
    t = team(client)
    url = f"/dependents/{t['dep']}/permissions/live_location"
    assert_error(client.put(url, json={"granted": True}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.put(url, json={"guardian_id": t["sid"]}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.put(url, json={"guardian_id": "nope", "granted": True}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_target_must_be_a_linked_secondary(client):
    t = team(client)
    stranger, sgid, _ = make_guardian(client, 4)
    assert_error(put(client, t["pt"], t["dep"], "live_location", sgid, True), 404, "SECONDARY_NOT_FOUND")
    assert_error(put(client, t["pt"], t["dep"], "live_location", str(uuid.uuid4()), True), 404, "SECONDARY_NOT_FOUND")
    assert_error(put(client, t["pt"], t["dep"], "live_location", t["pid"], False), 400, "PRIMARY_NOT_GOVERNABLE")


# ------------------------------------------------- per-dependent independence

def test_permissions_are_independent_per_dependent(client):
    # one Secondary account linked to two different Dependents (FR-B4)
    t = team(client)
    p2, p2id, _ = make_guardian(client, 2)
    dep2 = make_dependent(client, 2)
    assert link(client, p2, dep2).status_code == 201
    inv = invite(client, p2, dep2, "+923003330001")  # the same Secondary's phone
    assert inv.status_code == 200, inv.text
    acc = client.post("/invitations/accept", json={"invite_token": inv.json()["invite_token"]}, headers=auth(t["st"]))
    assert acc.status_code == 201, acc.text

    assert put(client, t["pt"], t["dep"], "live_location", t["sid"], True).status_code == 200
    assert mine(client, t["st"], t["dep"]).json()["modules"]["live_location"] is True
    assert mine(client, t["st"], dep2).json()["modules"]["live_location"] is False  # untouched
    # and the first Primary cannot touch the second Dependent
    assert_error(put(client, t["pt"], dep2, "live_location", t["sid"], True), 403, "NOT_PRIMARY_GUARDIAN")


def test_dashboard_lists_every_secondary(client):
    t = team(client)
    st2, sid2, _ = make_secondary(client, t["pt"], t["dep"], 2)
    verify(client, st2)
    put(client, t["pt"], t["dep"], "emergency_alerts", sid2, True)
    secs = {s["guardian_id"]: s["modules"] for s in client.get(f"/dependents/{t['dep']}/permissions", headers=auth(t["pt"])).json()["secondaries"]}
    assert set(secs) == {t["sid"], sid2}
    assert secs[sid2]["emergency_alerts"] is True and secs[t["sid"]]["emergency_alerts"] is False


def test_my_permissions_needs_a_link(client):
    t = team(client)
    other, _, _ = make_guardian(client, 2)
    assert_error(mine(client, other, t["dep"]), 403, "NOT_LINKED_TO_DEPENDENT")


# -------------------------------------------------------------- audit (FR-N3)

def test_changes_are_audit_logged_once_each(client, db):
    t = team(client)
    put(client, t["pt"], t["dep"], "live_location", t["sid"], False)  # first-time revoke: nothing changed
    assert db.query(AuditLog).count() == 0
    put(client, t["pt"], t["dep"], "live_location", t["sid"], True)
    put(client, t["pt"], t["dep"], "live_location", t["sid"], True)  # no change: no new entry
    put(client, t["pt"], t["dep"], "live_location", t["sid"], False)
    rows = db.query(AuditLog).order_by(AuditLog.occurred_at).all()
    assert [r.action for r in rows] == ["permission_granted", "permission_revoked"]
    assert all(str(r.actor_id) == t["pid"] and r.target_type == "permission_grant" for r in rows)
    grant = db.query(PermissionGrant).one()
    assert rows[0].target_id == grant.grant_id


def test_failed_changes_are_not_logged(client, db):
    t = team(client)
    put(client, t["st"], t["dep"], "live_location", t["sid"], True)  # forbidden
    put(client, t["pt"], t["dep"], "nonsense", t["sid"], True)  # invalid
    assert db.query(AuditLog).count() == 0 and db.query(PermissionGrant).count() == 0


# ---------------------------------------------------------------- race

def test_simultaneous_first_grants_create_one_row(client, engine, db, monkeypatch):
    t = team(client)
    pid, sid, dep = uuid.UUID(t["pid"]), uuid.UUID(t["sid"]), uuid.UUID(t["dep"])
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(4)
    original = permission_service._my_link

    def paused(db_, guardian_id, dependent_id):
        link_ = original(db_, guardian_id, dependent_id)
        try:
            barrier.wait(timeout=1.0)  # every request waits here, so all see "no grant row yet"
        except threading.BrokenBarrierError:
            pass
        return link_

    monkeypatch.setattr(permission_service, "_my_link", paused)

    def attempt(_):
        s = Session()
        try:
            user = s.get(User, pid)
            return permission_service.set_permission(s, user, dep, "live_location", sid, True).granted
        except AppError as exc:
            return exc.code
        except Exception as exc:  # an unhandled IntegrityError would show up here
            return type(exc).__name__
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results == [True] * 4, results
    assert db.query(PermissionGrant).count() == 1
    assert db.query(AuditLog).count() == 1  # granted once, not four times
