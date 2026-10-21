"""
Task 6.7 tests: account closure and the data retention job (FR-O1).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.core import scheduler
from app.core.config import get_settings
from app.core.database import Base
from app.models import AuditLog, DependentProfile, GuardianDependentLink, Message, PermissionGrant, PushToken, User
from app.services import call_provider, retention_service
from tests.test_audit_log import log
from tests.test_geofence import zone
from tests.test_linkage import PASSWORD, assert_error, auth, login
from tests.test_location import send, team
from tests.test_medication import add as add_med
from tests.test_messaging import send as send_msg
from tests.test_notifications import inbox
from tests.test_records import PDF, add as add_record, files_on_disk, ok, share, store  # noqa: F401 (store is an autouse fixture)
from tests.test_vitals import vadd
from tests.test_wellness import add as add_wellness


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setattr(call_provider, "_provider", call_provider.MockCallProvider())


def close_guardian(client, token, password=PASSWORD):
    return client.post("/account/close", json={"password": password}, headers=auth(token))


def close_dep(client, t, token=None, password=PASSWORD):
    return client.post(f"/dependents/{t['dep']}/close", json={"password": password}, headers=auth(token or t["pt"]))


def reopen_dep(client, t, token=None, password=PASSWORD):
    return client.post(f"/dependents/{t['dep']}/reopen", json={"password": password}, headers=auth(token or t["pt"]))


def make_due(db, user_id, days_ago=1):
    db.execute(text("UPDATE users SET delete_after = :d WHERE user_id = :u"), {"d": datetime.now(timezone.utc) - timedelta(days=days_ago), "u": str(user_id)})
    db.commit()


def user(db, uid):
    db.expire_all()
    return db.get(User, uid)


# ------------------------------------------------------------ the safety net

def test_every_table_has_a_retention_decision():
    """A new table fails here until someone decides what happens to it when an account is deleted."""
    assert set(Base.metadata.tables) == set(retention_service.HANDLED)
    owned = {m.__tablename__ for m in retention_service.DEPENDENT_TABLES}
    elsewhere = {"audit_logs", "guardian_dependent_links", "medication_schedules", "wellness_check_schedules"}
    for t in Base.metadata.tables.values():
        if "dependent_id" in t.c:
            assert t.name in owned | elsewhere, f"{t.name} has a dependent_id but the retention job does not delete it"


# ------------------------------------------------------------ a Guardian closes their own account

def test_secondary_closes_account(client, db):
    t = team(client)
    assert_error(close_guardian(client, t["st"], "wrong-password"), 403, "WRONG_PASSWORD")
    r = close_guardian(client, t["st"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "closed" and body["user_id"] == t["sid"]
    gap = datetime.fromisoformat(body["delete_after"]) - datetime.fromisoformat(body["closed_at"])
    assert gap == timedelta(days=get_settings().RETENTION_DAYS) == timedelta(days=60)
    # the old token stops working at once, sign-in and refresh say why
    assert_error(client.get("/auth/me", headers=auth(t["st"])), 403, "ACCOUNT_CLOSED")
    bad = client.post("/auth/login", json={"email": "s1@link-test.com", "password": PASSWORD})
    assert_error(bad, 403, "ACCOUNT_CLOSED")
    assert bad.json()["error"]["details"]["delete_after"] and bad.json()["error"]["details"]["role"] == "guardian"
    assert_error(client.post("/auth/login", json={"email": "s1@link-test.com", "password": "nope-nope-1"}), 401, "INVALID_CREDENTIALS")  # a wrong password learns nothing
    # the link is gone and the Primary was told and can read it in the history
    assert db.scalar(select(GuardianDependentLink.status).where(GuardianDependentLink.guardian_id == t["sid"])) == "revoked"
    assert [n for n in inbox(client, t["pt"])["items"] if n["type"] == "guardian_left"]
    assert "guardian_left" in [e["action"] for e in log(client, t["pt"], t["dep"]).json()["items"]]
    assert_error(close_guardian(client, t["st"]), 403, "ACCOUNT_CLOSED")


def test_primary_must_close_the_dependent_first(client):
    t = team(client)
    r = close_guardian(client, t["pt"])
    assert_error(r, 409, "CLOSE_DEPENDENTS_FIRST")
    assert r.json()["error"]["details"]["dependent_ids"] == [t["dep"]]
    assert_error(close_guardian(client, t["dt"]), 403, "FORBIDDEN")
    assert_error(client.post("/account/close", json={"password": PASSWORD}), 401, "NOT_AUTHENTICATED")


def test_reopen_a_guardian_account(client):
    t = team(client)
    assert close_guardian(client, t["st"]).status_code == 200
    assert_error(client.post("/account/reopen", json={"email": "s1@link-test.com", "password": "nope-nope-1"}), 401, "INVALID_CREDENTIALS")
    r = client.post("/account/reopen", json={"email": "s1@link-test.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert client.get("/auth/me", headers=auth(r.json()["access_token"])).status_code == 200
    assert_error(client.post("/account/reopen", json={"email": "s1@link-test.com", "password": PASSWORD}), 409, "NOT_CLOSED")
    # the link ended when the account was closed; the Primary has to invite again
    assert_error(client.get(f"/dependents/{t['dep']}/permissions/me", headers=auth(r.json()["access_token"])), 403, "NOT_LINKED_TO_DEPENDENT")


# ------------------------------------------------------------ the Primary closes a Dependent

def test_only_the_primary_closes_a_dependent(client):
    t = team(client)
    assert_error(close_dep(client, t, t["st"]), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(close_dep(client, t, t["dt"]), 403, "FORBIDDEN")
    assert_error(close_dep(client, t, password="wrong-password"), 403, "WRONG_PASSWORD")
    assert client.get("/auth/me", headers=auth(t["dt"])).status_code == 200  # nothing happened yet


def test_closing_a_dependent_stops_everything_and_reopening_restores_it(client, db, store):
    t = team(client)
    rec = ok(add_record(client, t["pt"], t["dep"], file=PDF))
    link_url = ok(share(client, t["pt"], t["dep"]))["url"]
    r = close_dep(client, t)
    assert r.status_code == 200 and r.json()["status"] == "closed"
    # the Dependent cannot use the old token or sign in
    assert_error(client.get("/auth/me", headers=auth(t["dt"])), 403, "ACCOUNT_CLOSED")
    assert_error(client.post("/auth/login", json={"email": "d1@link-test.com", "password": PASSWORD}), 403, "ACCOUNT_CLOSED")
    # no Guardian reaches the data any more, and doctor links are dead
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(t["pt"])), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(f"/dependents/{t['dep']}/vitals", headers=auth(t["st"])), 403, "NOT_LINKED_TO_DEPENDENT")
    assert client.get(link_url).status_code == 410  # the doctor link stopped at once
    assert [n for n in inbox(client, t["st"])["items"] if n["type"] == "dependent_closed"]
    # the Primary no longer has an active Dependent, so they may close their own account too ... but first reopen the Dependent
    assert_error(close_dep(client, t), 403, "NOT_LINKED_TO_DEPENDENT")  # already closed
    assert_error(reopen_dep(client, t, t["st"]), 403, "NOT_PRIMARY_GUARDIAN")  # a Secondary has no say
    assert_error(reopen_dep(client, t, password="wrong-password"), 403, "WRONG_PASSWORD")
    back = reopen_dep(client, t)
    assert back.status_code == 200 and back.json()["status"] == "reopened" and back.json()["delete_after"] is None
    login(client, "d1@link-test.com")
    assert client.get(f"/dependents/{t['dep']}/records", headers=auth(t["pt"])).status_code == 200
    assert client.get(f"/dependents/{t['dep']}/permissions/me", headers=auth(t["st"])).status_code == 200  # the Secondary is back too
    assert rec["record_id"]
    actions = [e["action"] for e in log(client, t["pt"], t["dep"]).json()["items"]]
    assert "dependent_account_closed" in actions and "dependent_account_reopened" in actions


def test_primary_can_close_own_account_after_closing_the_dependent(client):
    t = team(client)
    assert close_dep(client, t).status_code == 200
    assert close_guardian(client, t["pt"]).status_code == 200


def test_open_panic_is_resolved_when_the_dependent_is_closed(client, db):
    from tests.test_panic import press
    t = team(client)
    assert press(client, t).status_code in (200, 201)
    from app.models import EscalationEvent
    assert db.scalar(select(func.count()).select_from(EscalationEvent).where(EscalationEvent.status == "open")) == 1
    assert close_dep(client, t).status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(EscalationEvent).where(EscalationEvent.status == "open")) == 0


# ------------------------------------------------------------ the job

def populate(client, t):
    ok(vadd(client, t["dt"], t["dep"]))
    ok(add_record(client, t["pt"], t["dep"], file=PDF))
    ok(add_record(client, t["pt"], t["dep"], title="Note", notes="only a note"))
    assert client.post(f"/dependents/{t['dep']}/geofences", json=zone(), headers=auth(t["pt"])).status_code == 201
    assert add_med(client, t["pt"], t["dep"]).status_code == 201
    assert add_wellness(client, t["pt"], t).status_code == 201
    assert send(client, t).status_code in (200, 201)
    assert send_msg(client, t["pt"], t["dep"], "hello").status_code == 201
    assert client.post(f"/dependents/{t['dep']}/camera", json={"name": "Hall"}, headers=auth(t["dt"])).status_code == 201
    assert client.put(f"/dependents/{t['dep']}/emergency-contact", json={"name": "Aunt", "phone": "03001234567"}, headers=auth(t["pt"])).status_code in (200, 201)


def dep_rows(db, dep):
    """Rows left about this Dependent in every table that has a dependent_id (the audit trail is kept on purpose)."""
    left = {}
    for tbl in Base.metadata.tables.values():
        if "dependent_id" in tbl.c and tbl.name != "audit_logs":
            n = db.scalar(select(func.count()).select_from(tbl).where(tbl.c.dependent_id == dep))
            if n:
                left[tbl.name] = n
    return left


def test_the_job_deletes_a_closed_dependent_after_the_period(client, db, store):
    t = team(client)
    populate(client, t)
    dep = user(db, t["dep"]).user_id
    before = dep_rows(db, dep)
    assert {"vital_readings", "medical_records", "geofences", "medication_schedules", "wellness_check_schedules", "location_logs", "camera_devices", "guardian_dependent_links"} <= set(before)
    assert len(files_on_disk(store)) == 1
    assert db.scalar(select(func.count()).select_from(Message).where(Message.receiver_id == dep)) == 1
    assert close_dep(client, t).status_code == 200

    assert retention_service.sweep(db) == 0  # not due yet
    assert dep_rows(db, dep) == before
    make_due(db, dep, days_ago=0)
    assert retention_service.sweep(db) == 1
    db.expire_all()

    assert dep_rows(db, dep) == {}
    assert db.scalar(select(func.count()).select_from(Message).where((Message.receiver_id == dep) | (Message.sender_id == dep))) == 0
    assert files_on_disk(store) == []
    u = user(db, dep)
    assert u.purged_at is not None and u.full_name == "Deleted user" and u.email.startswith("deleted-") and u.email.endswith("@deleted.invalid")
    assert db.get(DependentProfile, dep).cnic is None
    assert db.scalar(select(func.count()).select_from(PermissionGrant)) == 0
    assert not [n for n in inbox(client, t["st"])["items"] if (n.get("data") or {}).get("dependent_id") == t["dep"]]
    # the audit trail is the exception: it stays, with the Dependent's id and no personal details
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.dependent_id == dep)) > 0
    # nothing more to do, and the old email is free / unusable
    assert retention_service.sweep(db) == 0
    assert_error(client.post("/auth/login", json={"email": "d1@link-test.com", "password": PASSWORD}), 401, "INVALID_CREDENTIALS")


def test_hold_and_reopen_stop_the_deletion(client, db):
    t = team(client)
    populate(client, t)
    dep = user(db, t["dep"]).user_id
    before = dep_rows(db, dep)
    assert close_dep(client, t).status_code == 200
    make_due(db, dep)
    db.execute(text("UPDATE users SET retention_hold = true WHERE user_id = :u"), {"u": str(dep)})
    db.commit()
    assert retention_service.sweep(db) == 0 and dep_rows(db, dep) == before  # on hold: an active audit or dispute
    db.execute(text("UPDATE users SET retention_hold = false WHERE user_id = :u"), {"u": str(dep)})
    db.commit()
    assert reopen_dep(client, t).status_code == 200
    assert retention_service.sweep(db) == 0 and dep_rows(db, dep) == before  # reopened in time
    assert retention_service.purge_user(db, dep, datetime.now(timezone.utc)) is False  # a stale job run is a no-op


def test_the_job_anonymizes_a_closed_guardian(client, db):
    t = team(client)
    assert close_guardian(client, t["st"]).status_code == 200
    sid = user(db, t["sid"]).user_id
    make_due(db, sid)
    assert retention_service.sweep(db) == 1
    db.expire_all()
    u = user(db, sid)
    assert u.purged_at and u.full_name == "Deleted user" and u.email.startswith("deleted-")
    assert db.scalar(select(func.count()).select_from(GuardianDependentLink).where(GuardianDependentLink.guardian_id == sid)) == 0
    assert db.scalar(select(func.count()).select_from(PushToken).where(PushToken.user_id == sid)) == 0
    # the Dependent and the Primary are not affected
    assert client.get(f"/dependents/{t['dep']}/permissions", headers=auth(t["pt"])).status_code == 200
    names = [e["actor"]["full_name"] for e in log(client, t["pt"], t["dep"]).json()["items"]]
    assert "Deleted user" in names


def test_the_audit_trail_is_removed_after_its_own_keep_time(client, db):
    t = team(client)
    assert close_dep(client, t).status_code == 200
    dep = user(db, t["dep"]).user_id
    make_due(db, dep)
    retention_service.sweep(db)
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.dependent_id == dep)) > 0
    db.execute(text("UPDATE users SET purged_at = :d WHERE user_id = :u"), {"d": datetime.now(timezone.utc) - timedelta(days=get_settings().AUDIT_RETENTION_DAYS + 1), "u": str(dep)})
    db.commit()
    retention_service.sweep(db)
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.dependent_id == dep)) == 0


def test_job_is_registered_with_the_scheduler():
    import app.main  # noqa: F401
    assert "retention_sweep" in [name for name, _ in scheduler.JOBS]
