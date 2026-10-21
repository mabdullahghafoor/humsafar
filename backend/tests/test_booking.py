"""
Task 6.2 tests: home-care booking requests and the shared Activity Timeline (FR-J1, FR-I2/J2).
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models import ActivityLog, AuditLog, BookingRequest, HealthcareOrganization as Org, HomeCareProvider as Prov
from tests.test_linkage import assert_error, auth, make_guardian
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_records import allow


def provider(db, name="Nurse Ayesha", **kw):
    p = Prov(name=name, specialization="nurse", contact=f"0300{abs(hash(name)) % 10**7:07d}", city="Lahore", service_charge=2500, **kw)
    db.add(p)
    db.commit()
    return p


def org(db, name="Edhi Ambulance", **kw):
    o = Org(name=name, type="ambulance", phone="115", city="Nationwide", **kw)
    db.add(o)
    db.commit()
    return o


def book(client, token, dep, provider_id, **body):
    return client.post(f"/dependents/{dep}/bookings", json={"provider_id": str(provider_id), **body}, headers=auth(token))


def act(client, token, dep, request_id, action):
    return client.post(f"/dependents/{dep}/bookings/{request_id}/{action}", headers=auth(token))


def contact(client, token, dep, org_id):
    return client.post(f"/dependents/{dep}/directory/contacts", json={"org_id": str(org_id)}, headers=auth(token))


def timeline(client, token, dep, **params):
    r = client.get(f"/dependents/{dep}/activity", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def in_days(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).isoformat()


def types(tl):
    return [i["type"] for i in tl["items"]]


# ---------------- access ----------------

def test_every_endpoint_needs_login(client):
    d = uuid.uuid4()
    r = uuid.uuid4()
    calls = [
        ("post", f"/dependents/{d}/bookings", {"provider_id": str(r)}), ("get", f"/dependents/{d}/bookings", None),
        ("get", f"/dependents/{d}/bookings/{r}", None), ("post", f"/dependents/{d}/bookings/{r}/confirm", None),
        ("post", f"/dependents/{d}/bookings/{r}/complete", None), ("post", f"/dependents/{d}/bookings/{r}/cancel", None),
        ("post", f"/dependents/{d}/directory/contacts", {"org_id": str(r)}), ("get", f"/dependents/{d}/activity", None),
    ]
    for method, path, body in calls:
        resp = getattr(client, method)(path, **({"json": body} if body else {}))
        assert_error(resp, 401, "NOT_AUTHENTICATED")


def test_dependent_and_primary_can_book_and_a_stranger_cannot(client, db):
    t = team(client)
    p = provider(db)
    assert book(client, t["dt"], t["dep"], p.provider_id).status_code == 201
    other = Prov(name="Other", specialization="nurse", contact="1", city="X")
    db.add(other)
    db.commit()
    assert book(client, t["pt"], t["dep"], other.provider_id).status_code == 201
    stranger, _, _ = make_guardian(client, 2)
    assert_error(book(client, stranger, t["dep"], p.provider_id), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get(f"/dependents/{t['dep']}/activity", headers=auth(stranger)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(book(client, t["dt"], uuid.uuid4(), p.provider_id), 403, "FORBIDDEN")


def test_secondary_needs_health_records_and_loses_it_at_once(client, db):
    t = team(client)
    p = provider(db)
    assert_error(book(client, t["st"], t["dep"], p.provider_id), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(f"/dependents/{t['dep']}/activity", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    r = book(client, t["st"], t["dep"], p.provider_id)
    assert r.status_code == 201 and r.json()["requested_by"] == t["sid"]
    allow(client, t, False)
    assert_error(client.get(f"/dependents/{t['dep']}/bookings", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(act(client, t["st"], t["dep"], r.json()["request_id"], "cancel"), 403, "MODULE_ACCESS_DENIED")


# ---------------- creating a request ----------------

def test_request_fields_and_first_timeline_entry(client, db):
    t = team(client)
    p = provider(db, "Physio Imran")
    when = in_days(3)
    r = book(client, t["dt"], t["dep"], p.provider_id, preferred_at=when, note="  Back exercises  ")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "pending" and j["provider_name"] == "Physio Imran" and j["specialization"] == "nurse"
    assert j["note"] == "Back exercises" and j["service_charge"] == 2500.0 and j["charge_unit"] == "per_visit"
    assert j["contact"] == p.contact and j["requested_by"] == t["dep"] and j["already_saved"] is False
    assert datetime.fromisoformat(j["preferred_at"]) == datetime.fromisoformat(when)
    one = client.get(f"/dependents/{t['dep']}/bookings/{j['request_id']}", headers=auth(t["dt"])).json()
    assert one["request_id"] == j["request_id"]
    tl = timeline(client, t["pt"], t["dep"])
    assert tl["total"] == 1
    e = tl["items"][0]
    assert e["type"] == "booking_request" and e["subject_name"] == "Physio Imran" and e["reference_id"] == j["request_id"]
    assert e["booking_status"] == "pending" and e["initiated_by"]["user_id"] == t["dep"] and e["initiated_by"]["role"] == "dependent"


def test_bad_input_is_refused(client, db):
    t = team(client)
    p = provider(db)
    hidden = provider(db, "Hidden", is_active=False)
    assert_error(book(client, t["dt"], t["dep"], uuid.uuid4()), 404, "PROVIDER_NOT_FOUND")
    assert_error(book(client, t["dt"], t["dep"], hidden.provider_id), 404, "PROVIDER_NOT_FOUND")
    for body in (
        {"preferred_at": in_days(-1)}, {"preferred_at": in_days(366)}, {"preferred_at": "2030-01-01T10:00:00"},
        {"note": "x" * 301}, {"note": "bad\x00text"}, {"client_id": "not-a-uuid"},
    ):
        assert_error(book(client, t["dt"], t["dep"], p.provider_id, **body), 422, "VALIDATION_ERROR")
    assert_error(client.post(f"/dependents/{t['dep']}/bookings", json={}, headers=auth(t["dt"])), 422, "VALIDATION_ERROR")
    assert_error(client.post(f"/dependents/{t['dep']}/bookings", json={"provider_id": "x"}, headers=auth(t["dt"])), 422, "VALIDATION_ERROR")
    assert book(client, t["dt"], t["dep"], p.provider_id, note="   ").json()["note"] is None
    assert db.scalar(select(func.count()).select_from(BookingRequest)) == 1


def test_one_open_request_per_provider_until_it_is_closed(client, db):
    t = team(client)
    p = provider(db)
    first = book(client, t["dt"], t["dep"], p.provider_id).json()
    assert_error(book(client, t["pt"], t["dep"], p.provider_id), 409, "BOOKING_ALREADY_OPEN")
    assert act(client, t["pt"], t["dep"], first["request_id"], "cancel").status_code == 200
    assert book(client, t["pt"], t["dep"], p.provider_id).status_code == 201


def test_safe_retry_with_client_id(client, db):
    t = team(client)
    p = provider(db)
    q = provider(db, "Second")
    cid = str(uuid.uuid4())
    a = book(client, t["dt"], t["dep"], p.provider_id, client_id=cid)
    b = book(client, t["dt"], t["dep"], p.provider_id, client_id=cid)
    assert a.status_code == 201 and b.status_code == 200 and b.json()["already_saved"] is True
    assert a.json()["request_id"] == b.json()["request_id"]
    assert_error(book(client, t["dt"], t["dep"], q.provider_id, client_id=cid), 409, "CLIENT_ID_REUSED")
    assert db.scalar(select(func.count()).select_from(BookingRequest)) == 1
    assert db.scalar(select(func.count()).select_from(ActivityLog)) == 1


def test_open_request_limit(client, db, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "BOOKING_MAX_OPEN", 2)
    ps = [provider(db, f"P{i}") for i in range(3)]
    assert book(client, t["dt"], t["dep"], ps[0].provider_id).status_code == 201
    second = book(client, t["dt"], t["dep"], ps[1].provider_id)
    assert second.status_code == 201
    assert_error(book(client, t["dt"], t["dep"], ps[2].provider_id), 409, "TOO_MANY_OPEN_BOOKINGS")
    assert act(client, t["dt"], t["dep"], second.json()["request_id"], "cancel").status_code == 200
    assert book(client, t["dt"], t["dep"], ps[2].provider_id).status_code == 201


def test_two_parallel_requests_to_the_same_provider_make_one(client, db):
    t = team(client)
    pid = provider(db).provider_id  # read now: the test session must not be used inside the threads
    gate = Barrier(2)

    def go(token):
        gate.wait()
        return book(client, token, t["dep"], pid).status_code

    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(go, [t["dt"], t["pt"]]))
    assert codes == [201, 409]
    assert db.scalar(select(func.count()).select_from(BookingRequest)) == 1
    assert db.scalar(select(func.count()).select_from(ActivityLog)) == 1


# ---------------- status changes ----------------

def test_status_flow_and_its_rules(client, db):
    t = team(client)
    p = provider(db)
    rid = book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"]
    assert_error(act(client, t["dt"], t["dep"], rid, "complete"), 409, "BOOKING_STATUS_CONFLICT")
    assert act(client, t["dt"], t["dep"], rid, "confirm").json()["status"] == "confirmed"
    assert_error(act(client, t["dt"], t["dep"], rid, "confirm"), 409, "BOOKING_STATUS_CONFLICT")
    assert act(client, t["dt"], t["dep"], rid, "complete").json()["status"] == "completed"
    for a in ("confirm", "complete", "cancel"):
        assert_error(act(client, t["dt"], t["dep"], rid, a), 409, "BOOKING_STATUS_CONFLICT")
    # a cancelled request is final too
    rid2 = book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"]
    assert act(client, t["pt"], t["dep"], rid2, "cancel").json()["status"] == "cancelled"
    for a in ("confirm", "complete", "cancel"):
        assert_error(act(client, t["dt"], t["dep"], rid2, a), 409, "BOOKING_STATUS_CONFLICT")
    assert types(timeline(client, t["pt"], t["dep"])) == ["booking_cancelled", "booking_request", "booking_completed", "booking_confirmed", "booking_request"]


def test_only_the_requester_or_the_primary_changes_a_request(client, db):
    t = team(client)
    allow(client, t)
    p = provider(db)
    rid = book(client, t["st"], t["dep"], p.provider_id).json()["request_id"]
    assert_error(act(client, t["dt"], t["dep"], rid, "confirm"), 403, "FORBIDDEN")  # the Dependent did not make it
    assert act(client, t["pt"], t["dep"], rid, "confirm").status_code == 200  # the Primary may
    q = provider(db, "Other")
    rid2 = book(client, t["dt"], t["dep"], q.provider_id).json()["request_id"]
    assert_error(act(client, t["st"], t["dep"], rid2, "cancel"), 403, "FORBIDDEN")  # a Secondary cannot change the Dependent's own
    assert act(client, t["dt"], t["dep"], rid2, "cancel").status_code == 200  # the requester may


def test_unknown_request_and_other_dependents_request(client, db):
    t = team(client)
    p = provider(db)
    assert_error(act(client, t["pt"], t["dep"], uuid.uuid4(), "cancel"), 404, "BOOKING_NOT_FOUND")
    assert_error(client.get(f"/dependents/{t['dep']}/bookings/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "BOOKING_NOT_FOUND")
    assert_error(client.get(f"/dependents/{t['dep']}/bookings/not-a-uuid", headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_list_bookings_filter_and_paging(client, db):
    t = team(client)
    ps = [provider(db, f"P{i}") for i in range(4)]
    ids = [book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"] for p in ps]
    act(client, t["dt"], t["dep"], ids[0], "confirm")
    act(client, t["dt"], t["dep"], ids[1], "cancel")
    r = client.get(f"/dependents/{t['dep']}/bookings", headers=auth(t["pt"])).json()
    assert r["total"] == 4 and [i["request_id"] for i in r["items"]] == ids[::-1]
    for status, n in (("pending", 2), ("confirmed", 1), ("cancelled", 1), ("completed", 0)):
        got = client.get(f"/dependents/{t['dep']}/bookings", params={"status": status}, headers=auth(t["pt"])).json()
        assert got["total"] == n and all(i["status"] == status for i in got["items"])
    page = client.get(f"/dependents/{t['dep']}/bookings", params={"limit": 3, "offset": 3}, headers=auth(t["pt"])).json()
    assert len(page["items"]) == 1 and page["total"] == 4
    assert_error(client.get(f"/dependents/{t['dep']}/bookings", params={"status": "weird"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


# ---------------- telling people ----------------

def kinds(client, token):
    return [n for n in inbox(client, token)["items"] if n["type"] == "booking_update"]


def test_others_are_told_but_not_the_person_who_acted(client, db):
    t = team(client)
    allow(client, t)
    p = provider(db)
    rid = book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"]
    for token in (t["pt"], t["st"]):
        n = kinds(client, token)
        assert len(n) == 1 and n[0]["priority"] == "standard" and "Nurse Ayesha" in n[0]["body"]
    assert kinds(client, t["dt"]) == []
    act(client, t["pt"], t["dep"], rid, "confirm")
    assert len(kinds(client, t["dt"])) == 1 and len(kinds(client, t["st"])) == 2 and len(kinds(client, t["pt"])) == 1


def test_a_secondary_without_permission_is_not_told(client, db):
    t = team(client)
    p = provider(db)
    book(client, t["dt"], t["dep"], p.provider_id)
    assert len(kinds(client, t["pt"])) == 1 and kinds(client, t["st"]) == []


# ---------------- organization contacts ----------------

def test_contact_is_logged_once_per_minute_per_person_and_organization(client, db):
    t = team(client)
    allow(client, t)
    o = org(db)
    a = contact(client, t["dt"], t["dep"], o.org_id)
    b = contact(client, t["dt"], t["dep"], o.org_id)
    assert a.status_code == 201 and b.status_code == 200 and a.json()["activity_id"] == b.json()["activity_id"]
    j = a.json()
    assert j["type"] == "org_contact" and j["subject_name"] == "Edhi Ambulance" and j["reference_id"] == str(o.org_id)
    assert j["initiated_by"]["role"] == "dependent" and j["booking_status"] is None
    assert contact(client, t["pt"], t["dep"], o.org_id).status_code == 201  # another person: its own entry
    assert contact(client, t["st"], t["dep"], o.org_id).status_code == 201
    assert timeline(client, t["pt"], t["dep"])["total"] == 3
    # after the dedupe window the same person logs again
    db.query(ActivityLog).update({ActivityLog.occurred_at: datetime.now(timezone.utc) - timedelta(seconds=get_settings().ACTIVITY_CONTACT_DEDUPE_S + 5)})
    db.commit()
    assert contact(client, t["dt"], t["dep"], o.org_id).status_code == 201


def test_contact_rules(client, db):
    t = team(client)
    o = org(db)
    hidden = org(db, "Hidden", is_active=False)
    assert_error(contact(client, t["st"], t["dep"], o.org_id), 403, "MODULE_ACCESS_DENIED")
    assert_error(contact(client, t["dt"], t["dep"], uuid.uuid4()), 404, "NOT_FOUND")
    assert_error(contact(client, t["dt"], t["dep"], hidden.org_id), 404, "NOT_FOUND")
    assert_error(client.post(f"/dependents/{t['dep']}/directory/contacts", json={}, headers=auth(t["dt"])), 422, "VALIDATION_ERROR")
    assert timeline(client, t["pt"], t["dep"])["total"] == 0


# ---------------- the unified timeline ----------------

def test_timeline_is_one_list_newest_first_with_roles(client, db):
    t = team(client)
    allow(client, t)
    o = org(db)
    p = provider(db)
    contact(client, t["dt"], t["dep"], o.org_id)
    rid = book(client, t["st"], t["dep"], p.provider_id).json()["request_id"]
    act(client, t["pt"], t["dep"], rid, "confirm")
    tl = timeline(client, t["pt"], t["dep"])
    assert types(tl) == ["booking_confirmed", "booking_request", "org_contact"]
    assert [i["initiated_by"]["role"] for i in tl["items"]] == ["primary", "secondary", "dependent"]
    assert all(i["booking_status"] in ("confirmed", None) for i in tl["items"])
    assert tl["items"][0]["booking_status"] == "confirmed" and tl["items"][2]["booking_status"] is None
    stamps = [i["occurred_at"] for i in tl["items"]]
    assert stamps == sorted(stamps, reverse=True)
    # the Dependent and a permitted Secondary see the same list
    assert timeline(client, t["dt"], t["dep"])["items"] == tl["items"] == timeline(client, t["st"], t["dep"])["items"]


def test_timeline_filters_and_paging(client, db):
    t = team(client)
    o = org(db)
    p = provider(db)
    contact(client, t["dt"], t["dep"], o.org_id)
    rid = book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"]
    act(client, t["dt"], t["dep"], rid, "cancel")
    assert timeline(client, t["pt"], t["dep"], type="org_contact")["total"] == 1
    assert timeline(client, t["pt"], t["dep"], type="booking_request")["total"] == 1
    assert timeline(client, t["pt"], t["dep"], type="booking_completed")["total"] == 0
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert timeline(client, t["pt"], t["dep"], **{"from": future})["total"] == 0
    assert timeline(client, t["pt"], t["dep"], **{"from": past})["total"] == 3
    assert timeline(client, t["pt"], t["dep"], to=past)["total"] == 0
    first = timeline(client, t["pt"], t["dep"], limit=2, offset=0)
    rest = timeline(client, t["pt"], t["dep"], limit=2, offset=2)
    assert first["total"] == rest["total"] == 3 and len(first["items"]) == 2 and len(rest["items"]) == 1
    assert not {i["activity_id"] for i in first["items"]} & {i["activity_id"] for i in rest["items"]}
    for params in ({"type": "weird"}, {"limit": 0}, {"limit": 201}, {"offset": -1}):
        assert_error(client.get(f"/dependents/{t['dep']}/activity", params=params, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_timeline_keeps_the_name_it_had_at_that_moment(client, db):
    t = team(client)
    p = provider(db, "Old Name")
    book(client, t["dt"], t["dep"], p.provider_id)
    db.query(Prov).update({Prov.name: "New Name"})
    db.commit()
    assert timeline(client, t["pt"], t["dep"])["items"][0]["subject_name"] == "Old Name"
    got = client.get(f"/dependents/{t['dep']}/bookings", headers=auth(t["pt"])).json()["items"][0]
    assert got["provider_name"] == "New Name"


def test_audit_rows_for_each_step(client, db):
    t = team(client)
    p = provider(db)
    rid = book(client, t["dt"], t["dep"], p.provider_id).json()["request_id"]
    act(client, t["dt"], t["dep"], rid, "confirm")
    act(client, t["dt"], t["dep"], rid, "complete")
    actions = [a for (a,) in db.execute(select(AuditLog.action).where(AuditLog.target_type == "booking_request").order_by(AuditLog.occurred_at))]
    assert actions == ["booking_requested", "booking_confirmed", "booking_completed"]


def test_database_rules(db, client):
    t = team(client)
    p = provider(db)
    base = dict(dependent_id=uuid.UUID(t["dep"]), provider_id=p.provider_id, requested_by=uuid.UUID(t["dep"]))
    db.add(BookingRequest(status="weird", **base))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(BookingRequest(note="  ", **base))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(ActivityLog(dependent_id=uuid.UUID(t["dep"]), initiated_by=uuid.UUID(t["dep"]), type="weird"))
    with pytest.raises(IntegrityError):
        db.commit()
