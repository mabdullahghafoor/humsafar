"""
Task 6.5 tests: transport security, production checks, rate limiting (SDS 17) and the encryption audit (FR-N1, FR-N2).
"""

import pytest
from sqlalchemy import select

from app.core import ratelimit, transport
from app.core.config import Settings, get_settings
from app.models import CameraClip, User
from app.scripts import security_audit as audit
from app.services import crypto_service, storage_service
from tests.test_linkage import PASSWORD, PHOTO, assert_error, auth, login, make_guardian, make_dependent, register
from tests.test_location import team


@pytest.fixture()
def limits_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_ENABLED", True)
    ratelimit.reset()


def bad_login(client, email="nobody@x-test.com"):
    return client.post("/auth/login", json={"email": email, "password": "wrong-password-1"})


# ------------------------------------------------------------ headers and https

def test_hardening_headers_on_every_response(client):
    for r in (client.get("/health"), client.get("/auth/me"), client.get("/does-not-exist")):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
        assert "strict-transport-security" not in h  # plain http: no HSTS


def test_enforce_https_refuses_plain_http(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "ENFORCE_HTTPS", True)
    assert_error(client.get("/auth/me"), 400, "HTTPS_REQUIRED")
    assert client.get("/health").status_code == 200  # the host's health check stays open
    r = client.get("https://testserver/auth/me")
    assert r.status_code == 401  # reaches the app
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")


def test_forwarded_proto_is_believed_only_behind_a_trusted_proxy(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "ENFORCE_HTTPS", True)
    fwd = {"X-Forwarded-Proto": "https"}
    assert_error(client.get("/auth/me", headers=fwd), 400, "HTTPS_REQUIRED")  # anyone can send that header
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True)
    r = client.get("/auth/me", headers=fwd)
    assert r.status_code == 401 and "strict-transport-security" in r.headers
    assert_error(client.get("/auth/me", headers={"X-Forwarded-Proto": "http"}), 400, "HTTPS_REQUIRED")


# ------------------------------------------------------------ production start-up checks

GOOD = dict(
    ENVIRONMENT="production", DEBUG=False, ENFORCE_HTTPS=True, JWT_SECRET_KEY="j" * 40, RECORDS_ENCRYPTION_KEY="k" * 40,
    DATABASE_URL="postgresql://u:p@db.example.com:5432/h?sslmode=require",
)


def test_production_checks():
    errors, _ = transport.production_problems(Settings(_env_file=None, **GOOD))
    assert errors == []
    for change, word in (
        ({"JWT_SECRET_KEY": "short"}, "JWT_SECRET_KEY"),
        ({"RECORDS_ENCRYPTION_KEY": ""}, "RECORDS_ENCRYPTION_KEY"), ({"DEBUG": True}, "DEBUG"), ({"ENFORCE_HTTPS": False}, "ENFORCE_HTTPS"),
        ({"RATE_LIMIT_ENABLED": False}, "RATE_LIMIT"), ({"DATABASE_URL": "postgresql://u:p@db.example.com:5432/h"}, "sslmode"),
        ({"DATABASE_URL": "postgresql://u:p@db.example.com:5432/h?sslmode=disable"}, "sslmode"),
    ):
        errors, _ = transport.production_problems(Settings(_env_file=None, **{**GOOD, **change}))
        assert any(word in e for e in errors), (change, errors)
    # a local database needs no sslmode
    errors, _ = transport.production_problems(Settings(_env_file=None, **{**GOOD, "DATABASE_URL": "postgresql://u:p@localhost/h"}))
    assert errors == []


def test_the_default_jwt_secret_is_refused_outside_development():
    with pytest.raises(Exception, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, **{**GOOD, "JWT_SECRET_KEY": "change-me-in-.env"})  # the older rule in config.py


def test_production_refuses_to_start_with_errors():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        transport.enforce_startup(Settings(_env_file=None, **{**GOOD, "JWT_SECRET_KEY": "x"}))
    transport.enforce_startup(Settings(_env_file=None, **GOOD))  # fine
    transport.enforce_startup(Settings(_env_file=None, ENVIRONMENT="development"))  # development never refuses


# ------------------------------------------------------------ rate limiting

def test_wrong_passwords_lock_one_email_for_a_while(client, limits_on, monkeypatch):
    assert register(client, "lock@x-test.com", "03001234501").status_code == 201
    for _ in range(8):
        assert_error(bad_login(client, "lock@x-test.com"), 401, "INVALID_CREDENTIALS")
    r = client.post("/auth/login", json={"email": "lock@x-test.com", "password": PASSWORD})  # even the right password is refused now
    assert_error(r, 429, "TOO_MANY_REQUESTS")
    assert int(r.headers["retry-after"]) >= 1 and r.json()["error"]["details"]["retry_after_s"] >= 1
    assert register(client, "other@x-test.com", "03001234502").status_code == 201
    assert client.post("/auth/login", json={"email": "other@x-test.com", "password": PASSWORD}).status_code == 200  # others unaffected
    t = [ratelimit._now()]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0] + 301)  # the window passes
    assert client.post("/auth/login", json={"email": "lock@x-test.com", "password": PASSWORD}).status_code == 200


def test_a_good_login_clears_the_count(client, limits_on):
    assert register(client, "clear@x-test.com", "03001234503").status_code == 201
    for _ in range(7):
        bad_login(client, "clear@x-test.com")
    assert client.post("/auth/login", json={"email": "clear@x-test.com", "password": PASSWORD}).status_code == 200
    for _ in range(7):
        assert bad_login(client, "clear@x-test.com").status_code == 401
    assert client.post("/auth/login", json={"email": "clear@x-test.com", "password": PASSWORD}).status_code == 200


def test_unknown_emails_are_limited_the_same_way(client, limits_on):
    for _ in range(8):
        assert bad_login(client, "ghost@x-test.com").status_code == 401
    assert_error(bad_login(client, "ghost@x-test.com"), 429, "TOO_MANY_REQUESTS")  # the same answer a real account gets: no way to tell them apart


def test_per_ip_limit_on_auth(client, limits_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "RATE_LOGIN_PER_MIN", 3)
    monkeypatch.setattr(get_settings(), "RATE_REGISTER_PER_MIN", 2)
    for i in range(3):
        assert bad_login(client, f"u{i}@x-test.com").status_code == 401
    assert_error(bad_login(client, "u9@x-test.com"), 429, "TOO_MANY_REQUESTS")
    assert register(client, "r1@x-test.com", "03001234511").status_code == 201
    assert register(client, "r2@x-test.com", "03001234512").status_code == 201
    assert_error(register(client, "r3@x-test.com", "03001234513"), 429, "TOO_MANY_REQUESTS")


def test_forwarded_for_counts_only_behind_a_trusted_proxy(client, limits_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "RATE_LOGIN_PER_MIN", 2)
    for i in range(2):
        assert bad_login(client, f"a{i}@x-test.com").status_code == 401
    h = {"X-Forwarded-For": "9.9.9.9"}
    assert client.post("/auth/login", json={"email": "z@x-test.com", "password": "wrong-password-1"}, headers=h).status_code == 429  # header ignored: same caller
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True)
    assert client.post("/auth/login", json={"email": "z@x-test.com", "password": "wrong-password-1"}, headers=h).status_code == 401  # a different address


def test_otp_cannot_be_guessed(client, limits_on):
    assert register(client, "otp@x-test.com", "03001234521").status_code == 201
    tok, _ = login_as(client, "otp@x-test.com")
    for _ in range(5):
        assert_error(client.post("/guardians/me/verify-phone/confirm", json={"code": "000000"}, headers=auth(tok)), 400, "OTP_INVALID")
    assert_error(client.post("/guardians/me/verify-phone/confirm", json={"code": get_settings().MOCK_OTP_CODE}, headers=auth(tok)), 429, "TOO_MANY_REQUESTS")


def login_as(client, email):
    return login(client, email)


def test_dependent_kyc_password_guessing_is_limited(client, limits_on):
    dep = make_dependent(client, 3)
    body = {"password": "wrong-password-1", "cnic": "42101-7654321-1", "liveness_image": PHOTO}
    for _ in range(5):
        assert client.post(f"/dependents/{dep}/kyc-verify", json=body).status_code in (400, 401, 403)
    assert_error(client.post(f"/dependents/{dep}/kyc-verify", json={**body, "password": PASSWORD}), 429, "TOO_MANY_REQUESTS")


def test_limiter_unit(monkeypatch, limits_on):
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0])
    for _ in range(3):
        ratelimit.hit("s", "k", 3, 60)
    with pytest.raises(Exception) as e:
        ratelimit.hit("s", "k", 3, 60)
    assert e.value.status_code == 429 and e.value.details["retry_after_s"] == 60
    t[0] += 61
    ratelimit.hit("s", "k", 3, 60)  # the old calls fell out of the window
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_ENABLED", False)
    for _ in range(50):
        ratelimit.hit("s2", "k", 1, 60)  # switched off


# ------------------------------------------------------------ encryption audit

def checks(db):
    db.expire_all()
    return {c.name: c for c in audit.run(db)}


def test_audit_is_clean_on_a_normal_database(client, db):
    team(client)
    c = checks(db)
    assert c["Passwords hashed"].status == "PASS" and c["Doctor-link secrets hashed"].status == "PASS"
    assert not [x for x in c.values() if x.status == "FAIL"]


def test_audit_catches_a_plain_password(client, db):
    team(client)
    db.query(User).update({"password_hash": "plain-text"})
    db.commit()
    assert checks(db)["Passwords hashed"].status == "FAIL"


def test_audit_catches_an_unencrypted_clip_file(client, db, tmp_path, monkeypatch):
    t = team(client)
    monkeypatch.setattr(get_settings(), "CLIPS_STORAGE_DIR", str(tmp_path))
    store = storage_service.get_storage("clips")
    key = store.save(b"\x00\x00\x00\x18ftypmp42 plain video", ".bin")
    import uuid
    db.add(CameraClip(dependent_id=uuid.UUID(t["dep"]), trigger_type="panic", status="stored", file_url=key, size_bytes=5, content_type="video/mp4"))
    db.commit()
    c = checks(db)["Camera clips encrypted on disk"]
    assert c.status == "FAIL" and "NOT encrypted" in c.detail
    (tmp_path / key).write_bytes(crypto_service.encrypt(b"video"))
    assert checks(db)["Camera clips encrypted on disk"].status == "PASS"


def test_inventory_names_the_stored_data():
    text = " ".join(" ".join(row) for row in audit.INVENTORY)
    for word in ("bcrypt", "AES-256-GCM", "TLS", "NOT end-to-end"):
        assert word in text
