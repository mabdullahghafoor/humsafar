"""
Task 1.3 tests: register, login, refresh, token handling, error envelope.
"""

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings
from app.models import GuardianDependentLink, GuardianProfile, DependentProfile, User

GOOD = {
    "email": "Ali.Khan@Example-Mail.com",
    "phone": "0300 1234567",
    "password": "correct-horse-9",
    "role": "guardian",
}


def register(client, **overrides):
    return client.post("/auth/register", json={**GOOD, **overrides})


def login(client, email="ali.khan@example-mail.com", password="correct-horse-9"):
    return client.post("/auth/login", json={"email": email, "password": password})


def assert_envelope(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code, body


def forge(payload_overrides=None, secret=None, algorithm="HS256", token_type="access"):
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "role": "guardian",
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(payload_overrides or {})
    return jwt.encode(payload, secret or s.JWT_SECRET_KEY, algorithm=algorithm)


# ----------------------------------------------------------------- register


def test_register_guardian_ok_and_normalised(client, db):
    r = register(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "ali.khan@example-mail.com"  # lower-cased
    assert body["phone"] == "+923001234567"  # normalised to E.164
    assert body["role"] == "guardian"
    assert body["guardian_role"] == "primary"  # FR-A1: independent registration = Primary
    assert "password" not in body and "password_hash" not in body
    assert db.get(GuardianProfile, __import__("uuid").UUID(body["user_id"])) is not None


def test_register_dependent_creates_dependent_profile(client, db):
    r = register(client, email="grandpa@example-mail.com", phone="+923111234567", role="dependent")
    assert r.status_code == 201, r.text
    assert r.json()["guardian_role"] is None
    assert db.get(DependentProfile, __import__("uuid").UUID(r.json()["user_id"])) is not None


def test_password_is_hashed_not_stored_plain(client, db):
    register(client)
    user = db.query(User).one()
    assert user.password_hash != GOOD["password"]
    assert user.password_hash.startswith("$2")  # bcrypt


def test_duplicate_email_rejected(client):
    assert register(client).status_code == 201
    r = register(client, phone="03111234567")
    assert_envelope(r, 409, "EMAIL_ALREADY_REGISTERED")


def test_same_phone_in_different_formats_is_a_duplicate(client):
    assert register(client, phone="03001234567").status_code == 201
    r = register(client, email="other@example-mail.com", phone="+92 300 1234567")
    assert_envelope(r, 409, "PHONE_ALREADY_REGISTERED")


def test_email_duplicate_is_case_insensitive(client):
    assert register(client).status_code == 201
    r = register(client, email="ALI.KHAN@EXAMPLE-MAIL.COM", phone="03111234567")
    assert_envelope(r, 409, "EMAIL_ALREADY_REGISTERED")


def test_validation_errors_use_envelope_with_field_names(client):
    r = client.post(
        "/auth/register",
        json={"email": "not-an-email", "phone": "12", "password": "short", "role": "admin"},
    )
    assert_envelope(r, 422, "VALIDATION_ERROR")
    fields = {f["field"] for f in r.json()["error"]["details"]["fields"]}
    assert {"email", "phone", "password", "role"} <= fields


def test_cannot_register_as_admin_or_pick_secondary(client):
    # FR-A1: guardian_role is never client-controlled at registration.
    r = register(client, guardian_role="secondary")
    assert r.status_code == 201
    assert r.json()["guardian_role"] == "primary"


def test_password_over_72_bytes_rejected(client):
    r = register(client, password="a" * 73)
    assert_envelope(r, 422, "VALIDATION_ERROR")


def test_missing_body_fields(client):
    assert_envelope(client.post("/auth/register", json={}), 422, "VALIDATION_ERROR")


# -------------------------------------------------------------------- login


def test_login_guardian_returns_token_pair(client):
    register(client)
    r = login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert body["user"]["email"] == "ali.khan@example-mail.com"
    s = get_settings()
    access = jwt.decode(body["access_token"], s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
    refresh = jwt.decode(body["refresh_token"], s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
    assert access["type"] == "access" and refresh["type"] == "refresh"
    assert access["sub"] == body["user"]["user_id"] == refresh["sub"]
    assert access["role"] == "guardian"


def test_login_email_is_case_insensitive(client):
    register(client)
    assert login(client, email="ALI.KHAN@example-mail.COM").status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client):
    register(client)
    wrong = login(client, password="not-the-password")
    unknown = login(client, email="nobody@example-mail.com")
    assert_envelope(wrong, 401, "INVALID_CREDENTIALS")
    assert_envelope(unknown, 401, "INVALID_CREDENTIALS")
    assert wrong.json() == unknown.json()  # no account enumeration


def test_dependent_cannot_login_until_activated(client, db):
    r = register(client, email="dep@example-mail.com", phone="03211234567", role="dependent")
    assert r.status_code == 201
    blocked = login(client, email="dep@example-mail.com")
    assert_envelope(blocked, 403, "ACCOUNT_NOT_ACTIVATED")
    # wrong password must NOT reveal activation state
    assert_envelope(login(client, email="dep@example-mail.com", password="nope-nope-1"), 401, "INVALID_CREDENTIALS")


def test_dependent_can_login_once_kyc_verified_and_linked_to_primary(client, db):
    import uuid

    g = register(client).json()
    d = register(client, email="dep@example-mail.com", phone="03211234567", role="dependent").json()

    # KYC verified but NOT linked yet -> still blocked (FR-A2 needs both)
    dep = db.get(DependentProfile, uuid.UUID(d["user_id"]))
    dep.liveness_status = "verified"
    db.commit()
    assert_envelope(login(client, email="dep@example-mail.com"), 403, "ACCOUNT_NOT_ACTIVATED")

    # Linked to an active Primary -> allowed
    db.add(
        GuardianDependentLink(
            guardian_id=uuid.UUID(g["user_id"]),
            dependent_id=uuid.UUID(d["user_id"]),
            role="primary",
            status="active",
        )
    )
    db.commit()
    ok = login(client, email="dep@example-mail.com")
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["role"] == "dependent"


# ---------------------------------------------------------------- /auth/me


def test_me_with_valid_access_token(client):
    register(client)
    token = login(client).json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "ali.khan@example-mail.com"


def test_me_without_token(client):
    r = client.get("/auth/me")
    assert_envelope(r, 401, "NOT_AUTHENTICATED")
    assert r.headers.get("www-authenticate") == "Bearer"


def test_me_with_garbage_token(client):
    assert_envelope(client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"}), 401, "TOKEN_INVALID")


def test_me_rejects_refresh_token_used_as_access(client):
    register(client)
    refresh_token = login(client).json()["refresh_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert_envelope(r, 401, "TOKEN_WRONG_TYPE")


def test_me_with_expired_token_says_expired(client):
    register(client)
    uid = login(client).json()["user"]["user_id"]
    expired = forge({"sub": uid, "exp": datetime.now(timezone.utc) - timedelta(seconds=5)})
    assert_envelope(client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}), 401, "TOKEN_EXPIRED")


def test_me_with_token_signed_by_wrong_secret(client):
    register(client)
    uid = login(client).json()["user"]["user_id"]
    bad = forge({"sub": uid}, secret="a-completely-different-secret-key-0123456789")
    assert_envelope(client.get("/auth/me", headers={"Authorization": f"Bearer {bad}"}), 401, "TOKEN_INVALID")


def test_me_rejects_unsigned_alg_none_token(client):
    register(client)
    uid = login(client).json()["user"]["user_id"]
    now = datetime.now(timezone.utc)
    unsigned = jwt.encode(
        {"sub": uid, "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}, key=None, algorithm="none"
    )
    assert_envelope(client.get("/auth/me", headers={"Authorization": f"Bearer {unsigned}"}), 401, "TOKEN_INVALID")


def test_me_for_deleted_user_is_rejected(client, db):
    register(client)
    login_body = login(client).json()
    db.query(GuardianProfile).delete()
    db.query(User).delete()
    db.commit()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {login_body['access_token']}"})
    assert_envelope(r, 401, "TOKEN_INVALID")


# ------------------------------------------------------------ /auth/refresh


def test_refresh_returns_new_working_pair(client):
    register(client)
    first = login(client).json()
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["access_token"] != first["access_token"]
    assert new["refresh_token"] != first["refresh_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"})
    assert me.status_code == 200


def test_refresh_rejects_access_token(client):
    register(client)
    access = login(client).json()["access_token"]
    assert_envelope(client.post("/auth/refresh", json={"refresh_token": access}), 401, "TOKEN_WRONG_TYPE")


def test_refresh_rejects_garbage_and_expired(client):
    register(client)
    uid = login(client).json()["user"]["user_id"]
    assert_envelope(client.post("/auth/refresh", json={"refresh_token": "junk"}), 401, "TOKEN_INVALID")
    expired = forge({"sub": uid, "exp": datetime.now(timezone.utc) - timedelta(seconds=5)}, token_type="refresh")
    assert_envelope(client.post("/auth/refresh", json={"refresh_token": expired}), 401, "TOKEN_EXPIRED")


def test_refresh_requires_body(client):
    assert_envelope(client.post("/auth/refresh", json={}), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------- misc / shape


def test_unknown_route_uses_envelope(client):
    assert_envelope(client.get("/nope"), 404, "NOT_FOUND")


def test_health_still_works(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/db").json() == {"database": "connected"}
