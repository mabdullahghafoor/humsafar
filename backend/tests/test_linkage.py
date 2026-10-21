"""
Task 1.5 tests: guardian-dependent linkage, invitations, caps (FR-B1, FR-B2, FR-B4).
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import GuardianDependentLink, GuardianProfile, User
from app.schemas.auth import normalize_phone
from app.services import linkage_service

PASSWORD = "correct-horse-9"
PHOTO = "VGhpcyBpcyBhIHBob3Rv"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code, body


def register(client, email, phone, role="guardian", invite_token=None):
    body = {"email": email, "phone": phone, "password": PASSWORD, "full_name": "Test User", "role": role}
    if invite_token:
        body["invite_token"] = invite_token
    return client.post("/auth/register", json=body)


def login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()["user"]["user_id"]


def make_guardian(client, n, verified=True):
    """A primary-designated guardian, optionally verified (CNIC check)."""
    email, phone = f"g{n}@link-test.com", f"030022200{n:02d}"
    assert register(client, email, phone).status_code == 201
    token, gid = login(client, email)
    if verified:
        r = client.post("/guardians/me/verify-cnic", json={"cnic": "42101-1234567-1"}, headers=auth(token))
        assert r.json()["verified"] is True
    return token, gid, phone


def make_dependent(client, n):
    r = register(client, f"d{n}@link-test.com", f"032122200{n:02d}", role="dependent")
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def link(client, token, dep):
    return client.post(f"/dependents/{dep}/link", headers=auth(token))


def invite(client, token, dep, phone):
    return client.post(f"/dependents/{dep}/guardians/invite", json={"phone": phone}, headers=auth(token))


def make_secondary(client, primary_token, dep, n):
    """Primary invites a new phone; the invitee registers with the token. Returns (token, id, phone)."""
    phone = f"030033300{n:02d}"
    inv = invite(client, primary_token, dep, phone)
    assert inv.status_code == 200, inv.text
    r = register(client, f"s{n}@link-test.com", phone, invite_token=inv.json()["invite_token"])
    assert r.status_code == 201, r.text
    token, sid = login(client, f"s{n}@link-test.com")
    return token, sid, phone


def forged_invite(dep, inviter, phone, exp_delta=timedelta(days=1), token_type="invite"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(dep), "inviter": str(inviter), "phone": phone, "type": token_type,
        "iat": now, "exp": now + exp_delta, "jti": uuid.uuid4().hex,
    }
    s = get_settings()
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def widen_race_window(monkeypatch, parties):
    """
    Make every request pause right after it has counted the Dependent's Guardians, until
    all `parties` requests have counted. Without a row lock they would all see the same
    count and all insert (the bug). With the lock only one request is ever inside this
    window, so the barrier simply times out and the requests run one after another.
    """
    barrier = threading.Barrier(parties)
    original = linkage_service._active_links

    def paused(db, dependent_id):
        links = original(db, dependent_id)
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            pass
        return links

    monkeypatch.setattr(linkage_service, "_active_links", paused)


# --------------------------------------------------------------- primary link


def test_link_requires_a_token(client):
    assert_error(client.post(f"/dependents/{uuid.uuid4()}/link"), 401, "NOT_AUTHENTICATED")


def test_unverified_guardian_cannot_link(client):
    token, _, _ = make_guardian(client, 1, verified=False)
    dep = make_dependent(client, 1)
    assert_error(link(client, token, dep), 403, "GUARDIAN_NOT_VERIFIED")


def test_dependent_token_cannot_link(client):
    dep = make_dependent(client, 1)
    token = security.create_access_token(uuid.UUID(dep), "dependent")
    assert_error(link(client, token, dep), 403, "FORBIDDEN")


def test_verified_primary_links_dependent(client, db):
    token, gid, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    r = link(client, token, dep)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "primary" and body["status"] == "active"
    assert body["guardian_id"] == gid and body["dependent_id"] == dep


def test_full_flow_register_kyc_link_then_dependent_can_login(client):
    token, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    # verified but not linked: still blocked
    k = client.post(
        f"/dependents/{dep}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-7654321-1", "liveness_image": PHOTO}
    )
    assert k.json()["status"] == "verified"
    blocked = client.post("/auth/login", json={"email": "d1@link-test.com", "password": PASSWORD})
    assert_error(blocked, 403, "ACCOUNT_NOT_ACTIVATED")
    assert link(client, token, dep).status_code == 201
    ok = client.post("/auth/login", json={"email": "d1@link-test.com", "password": PASSWORD})
    assert ok.status_code == 200, ok.text


def test_link_twice_is_rejected(client):
    token, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    assert link(client, token, dep).status_code == 201
    assert_error(link(client, token, dep), 409, "ALREADY_LINKED")


def test_second_primary_is_rejected(client):
    t1, _, _ = make_guardian(client, 1)
    t2, _, _ = make_guardian(client, 2)
    dep = make_dependent(client, 1)
    assert link(client, t1, dep).status_code == 201
    assert_error(link(client, t2, dep), 409, "PRIMARY_ALREADY_EXISTS")


def test_unknown_dependent_and_guardian_id_are_not_found(client):
    token, gid, _ = make_guardian(client, 1)
    assert_error(link(client, token, uuid.uuid4()), 404, "DEPENDENT_NOT_FOUND")
    assert_error(link(client, token, gid), 404, "DEPENDENT_NOT_FOUND")


def test_bad_uuid_path(client):
    token, _, _ = make_guardian(client, 1)
    assert_error(link(client, token, "not-a-uuid"), 422, "VALIDATION_ERROR")


def test_primary_can_link_multiple_dependents(client):
    token, _, _ = make_guardian(client, 1)
    d1, d2 = make_dependent(client, 1), make_dependent(client, 2)
    assert link(client, token, d1).status_code == 201
    assert link(client, token, d2).status_code == 201
    r = client.get("/guardians/me/dependents", headers=auth(token))
    assert r.status_code == 200, r.text
    assert {d["dependent_id"] for d in r.json()} == {d1, d2}
    assert all(d["my_role"] == "primary" for d in r.json())


# ------------------------------------------------------------------ invitations


def test_invite_register_creates_secondary_with_link(client, db):
    pt, pid, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    phone = "03003330001"
    inv = invite(client, pt, dep, phone)
    assert inv.status_code == 200, inv.text
    body = inv.json()
    assert body["invited_phone"] == "+923003330001" and body["expires_in"] == 7 * 24 * 3600

    r = register(client, "s1@link-test.com", phone, invite_token=body["invite_token"])
    assert r.status_code == 201, r.text
    assert r.json()["guardian_role"] == "secondary"

    st, sid = login(client, "s1@link-test.com")
    mine = client.get("/guardians/me/dependents", headers=auth(st)).json()
    assert [d["dependent_id"] for d in mine] == [dep] and mine[0]["my_role"] == "secondary"

    team = client.get(f"/dependents/{dep}/guardians", headers=auth(pt)).json()
    assert [(g["guardian_role"], g["guardian_id"]) for g in team] == [("primary", pid), ("secondary", sid)]


def test_unverified_primary_cannot_invite(client):
    token, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, token, dep)
    other, _, _ = make_guardian(client, 2, verified=False)
    assert_error(invite(client, other, dep, "03003330001"), 403, "GUARDIAN_NOT_VERIFIED")


def test_only_this_dependents_primary_can_invite(client):
    p1, _, _ = make_guardian(client, 1)
    p2, _, _ = make_guardian(client, 2)
    d1, d2 = make_dependent(client, 1), make_dependent(client, 2)
    link(client, p1, d1)
    link(client, p2, d2)
    assert_error(invite(client, p2, d1, "03003330001"), 403, "NOT_PRIMARY_GUARDIAN")


def test_secondary_cannot_invite_or_link(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    st, _, _ = make_secondary(client, pt, dep, 1)
    client.post("/guardians/me/verify-cnic", json={"cnic": "42101-1234567-1"}, headers=auth(st))
    assert_error(invite(client, st, dep, "03003330002"), 403, "NOT_PRIMARY_GUARDIAN")
    other_dep = make_dependent(client, 2)
    assert_error(link(client, st, other_dep), 403, "SECONDARY_CANNOT_LINK")


def test_invite_wrong_phone_cannot_register(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    token = invite(client, pt, dep, "03003330001").json()["invite_token"]
    r = register(client, "thief@link-test.com", "03003339999", invite_token=token)
    assert_error(r, 403, "INVITE_NOT_FOR_YOU")


def test_bad_invite_tokens_on_register(client):
    pt, pid, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    phone = "+923003330001"
    garbage = register(client, "a@link-test.com", "03003330001", invite_token="not.a.jwt")
    assert_error(garbage, 400, "INVITE_INVALID")
    expired = forged_invite(dep, pid, phone, exp_delta=timedelta(seconds=-5))
    assert_error(register(client, "a@link-test.com", "03003330001", invite_token=expired), 400, "INVITE_EXPIRED")
    wrong_type = forged_invite(dep, pid, phone, token_type="access")
    assert_error(register(client, "a@link-test.com", "03003330001", invite_token=wrong_type), 400, "INVITE_INVALID")
    # signed by an unrelated person who is not this Dependent's Primary
    stranger = forged_invite(dep, uuid.uuid4(), phone)
    assert_error(register(client, "a@link-test.com", "03003330001", invite_token=stranger), 400, "INVITE_INVALID")
    # nothing was created by any failed attempt
    assert client.post("/auth/login", json={"email": "a@link-test.com", "password": PASSWORD}).status_code == 401


def test_invite_token_not_allowed_for_dependent_registration(client):
    r = register(client, "x@link-test.com", "03213330001", role="dependent", invite_token="whatever")
    assert_error(r, 422, "VALIDATION_ERROR")


def test_invite_token_cannot_be_used_as_a_login_token(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    token = invite(client, pt, dep, "03003330001").json()["invite_token"]
    assert_error(client.get("/auth/me", headers=auth(token)), 401, "TOKEN_WRONG_TYPE")


def test_invite_to_ineligible_phones_gets_one_generic_answer(client):
    pt, _, own_phone = make_guardian(client, 1)
    other_primary_token, _, other_primary_phone = make_guardian(client, 2)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    make_dependent(client, 2)  # a Dependent account's phone: 032122200 02
    for phone in (own_phone, other_primary_phone, "03212220002"):
        assert_error(invite(client, pt, dep, phone), 409, "INVITEE_NOT_ELIGIBLE")


def test_invite_phone_validation(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    assert_error(invite(client, pt, dep, "12"), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------------ cap (FR-B2)


def test_fourth_guardian_is_rejected_at_invite(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    make_secondary(client, pt, dep, 1)
    make_secondary(client, pt, dep, 2)
    assert_error(invite(client, pt, dep, "03003330003"), 409, "GUARDIAN_CAP_REACHED")


def test_cap_also_enforced_when_invites_were_issued_earlier(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    tokens = [invite(client, pt, dep, f"030033300{i:02d}").json()["invite_token"] for i in (1, 2, 3)]
    r1 = register(client, "s1@link-test.com", "03003330001", invite_token=tokens[0])
    r2 = register(client, "s2@link-test.com", "03003330002", invite_token=tokens[1])
    r3 = register(client, "s3@link-test.com", "03003330003", invite_token=tokens[2])
    assert (r1.status_code, r2.status_code) == (201, 201)
    assert_error(r3, 409, "GUARDIAN_CAP_REACHED")
    # the failed registration left no half-created account behind
    assert client.post("/auth/login", json={"email": "s3@link-test.com", "password": PASSWORD}).status_code == 401


def test_team_listing_has_one_primary_and_two_secondaries(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    make_secondary(client, pt, dep, 1)
    make_secondary(client, pt, dep, 2)
    team = client.get(f"/dependents/{dep}/guardians", headers=auth(pt)).json()
    assert [g["guardian_role"] for g in team] == ["primary", "secondary", "secondary"]


def test_listing_guardians_needs_to_be_linked(client):
    p1, _, _ = make_guardian(client, 1)
    p2, _, _ = make_guardian(client, 2)
    dep = make_dependent(client, 1)
    link(client, p1, dep)
    assert_error(client.get(f"/dependents/{dep}/guardians", headers=auth(p2)), 403, "NOT_LINKED_TO_DEPENDENT")


# ---------------------------------------------- existing secondary, many dependents


def test_existing_secondary_accepts_second_invitation(client):
    p1, _, _ = make_guardian(client, 1)
    p2, _, _ = make_guardian(client, 2)
    d1, d2 = make_dependent(client, 1), make_dependent(client, 2)
    link(client, p1, d1)
    link(client, p2, d2)
    st, _, phone = make_secondary(client, p1, d1, 1)
    token = invite(client, p2, d2, phone).json()["invite_token"]  # existing secondary is eligible
    r = client.post("/invitations/accept", json={"invite_token": token}, headers=auth(st))
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "secondary" and r.json()["dependent_id"] == d2
    mine = client.get("/guardians/me/dependents", headers=auth(st)).json()
    assert {d["dependent_id"] for d in mine} == {d1, d2}


def test_primary_account_cannot_accept_a_secondary_invitation(client):
    p1, _, _ = make_guardian(client, 1)
    other, _, _ = make_guardian(client, 2)
    dep = make_dependent(client, 1)
    link(client, p1, dep)
    token = invite(client, p1, dep, "03003330001").json()["invite_token"]
    r = client.post("/invitations/accept", json={"invite_token": token}, headers=auth(other))
    assert_error(r, 403, "PRIMARY_CANNOT_ACCEPT_INVITE")


def test_accept_with_someone_elses_invitation(client):
    p1, _, _ = make_guardian(client, 1)
    p2, _, _ = make_guardian(client, 2)
    d1, d2 = make_dependent(client, 1), make_dependent(client, 2)
    link(client, p1, d1)
    link(client, p2, d2)
    st1, _, phone1 = make_secondary(client, p1, d1, 1)
    st2, _, _ = make_secondary(client, p1, d1, 2)
    token_for_1 = invite(client, p2, d2, phone1).json()["invite_token"]
    r = client.post("/invitations/accept", json={"invite_token": token_for_1}, headers=auth(st2))
    assert_error(r, 403, "INVITE_NOT_FOR_YOU")


def test_accept_same_dependent_twice(client):
    pt, _, _ = make_guardian(client, 1)
    dep = make_dependent(client, 1)
    link(client, pt, dep)
    st, _, phone = make_secondary(client, pt, dep, 1)
    inviter = uuid.UUID(client.get("/auth/me", headers=auth(pt)).json()["user_id"])
    stale = forged_invite(dep, inviter, normalize_phone(phone))  # tokens carry the normalised phone
    assert_error(client.post("/invitations/accept", json={"invite_token": stale}, headers=auth(st)), 409, "ALREADY_LINKED")


# ----------------------------------------------------- concurrency (real races)


def test_two_simultaneous_primary_links_only_one_wins(client, engine, monkeypatch):
    _, g1, _ = make_guardian(client, 1)
    _, g2, _ = make_guardian(client, 2)
    dep = uuid.UUID(make_dependent(client, 1))
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    widen_race_window(monkeypatch, 2)

    def attempt(guardian_id):
        s = Session()
        try:
            user = s.get(User, uuid.UUID(guardian_id))
            linkage_service.link_primary(s, user, dep)
            return "linked"
        except AppError as exc:
            return exc.code
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(attempt, [g1, g2]))
    assert results == ["PRIMARY_ALREADY_EXISTS", "linked"]
    s = Session()
    assert s.query(GuardianDependentLink).filter_by(dependent_id=dep, role="primary").count() == 1
    s.close()


def test_three_simultaneous_secondary_joins_respect_the_cap(client, engine, db, monkeypatch):
    pt, pid, _ = make_guardian(client, 1)
    dep = uuid.UUID(make_dependent(client, 1))
    link(client, pt, str(dep))
    # three existing secondary-designated accounts all trying to join at once
    secondary_ids = []
    for i in range(3):
        u = User(email=f"race{i}@link-test.com", phone=f"+92300444000{i}", password_hash="x", role="guardian")
        db.add(u)
        db.flush()
        db.add(GuardianProfile(user_id=u.user_id, guardian_role="secondary"))
        secondary_ids.append(u.user_id)
    db.commit()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    widen_race_window(monkeypatch, 3)

    def attempt(guardian_id):
        s = Session()
        try:
            linkage_service.attach_secondary(s, guardian_id, dep)
            s.commit()
            return "joined"
        except AppError as exc:
            s.rollback()
            return exc.code
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = sorted(pool.map(attempt, secondary_ids))
    assert results == ["GUARDIAN_CAP_REACHED", "joined", "joined"]
    s = Session()
    assert s.query(GuardianDependentLink).filter_by(dependent_id=dep, status="active").count() == 3
    s.close()
