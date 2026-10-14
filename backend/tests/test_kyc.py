"""
Task 1.4 tests: mocked KYC for Dependents (FR-A2) and Guardians (FR-A3).
"""

import uuid

from fastapi import Depends

from app.core import security
from app.core.deps import require_verified_guardian
from app.main import app
from app.models import DependentProfile, GuardianDependentLink, GuardianProfile, User

PASSWORD = "correct-horse-9"
PHOTO = "VGhpcyBpcyBhIHBsYXVzaWJsZSBiYXNlNjQgcGhvdG8="  # any non-empty base64-ish text
GOOD_CNIC = "42101-1234567-1"


def register(client, email, phone, role):
    r = client.post("/auth/register", json={"email": email, "phone": phone, "password": PASSWORD, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


def guardian_token(client, email="guardian@kyc-test.com", phone="03001110001"):
    register(client, email, phone, "guardian")
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()["user"]["user_id"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def new_dependent(client, n=1):
    return register(client, f"dep{n}@kyc-test.com", f"0321111000{n}", "dependent")["user_id"]


def kyc(client, dep_id, cnic=GOOD_CNIC, photo=PHOTO, password=PASSWORD):
    return client.post(
        f"/dependents/{dep_id}/kyc-verify", json={"password": password, "cnic": cnic, "liveness_image": photo}
    )


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code, body


# ------------------------------------------------------------ dependent KYC


def test_dependent_kyc_verified_but_not_active_until_linked(client, db):
    dep = new_dependent(client)
    r = kyc(client, dep)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "verified"
    assert body["account_active"] is False
    assert body["next_step"] == "link_primary_guardian"
    profile = db.get(DependentProfile, uuid.UUID(dep))
    assert profile.liveness_status == "verified"
    assert profile.cnic == GOOD_CNIC
    # still cannot log in (FR-A2: needs the Primary link too)
    login = client.post("/auth/login", json={"email": "dep1@kyc-test.com", "password": PASSWORD})
    assert_error(login, 403, "ACCOUNT_NOT_ACTIVATED")


def test_full_flow_register_kyc_link_login(client, db):
    _, guardian_id = guardian_token(client)
    dep = new_dependent(client)
    assert kyc(client, dep).json()["status"] == "verified"
    db.add(
        GuardianDependentLink(
            guardian_id=uuid.UUID(guardian_id), dependent_id=uuid.UUID(dep), role="primary", status="active"
        )
    )
    db.commit()
    login = client.post("/auth/login", json={"email": "dep1@kyc-test.com", "password": PASSWORD})
    assert login.status_code == 200, login.text


def test_already_linked_dependent_is_active_straight_after_kyc(client, db):
    _, guardian_id = guardian_token(client)
    dep = new_dependent(client)
    db.add(
        GuardianDependentLink(
            guardian_id=uuid.UUID(guardian_id), dependent_id=uuid.UUID(dep), role="primary", status="active"
        )
    )
    db.commit()
    body = kyc(client, dep).json()
    assert body["account_active"] is True and body["next_step"] == "none"


def test_cnic_without_dashes_is_normalised(client, db):
    dep = new_dependent(client)
    assert kyc(client, dep, cnic="4210112345671").status_code == 200
    assert db.get(DependentProfile, uuid.UUID(dep)).cnic == "42101-1234567-1"


def test_invalid_cnic_rejected(client):
    dep = new_dependent(client)
    for bad in ["123", "42101-12345-1", "abcde-1234567-1", "02101-1234567-1", ""]:
        assert_error(kyc(client, dep, cnic=bad), 422, "VALIDATION_ERROR")


def test_missing_liveness_photo_rejected(client):
    dep = new_dependent(client)
    r = client.post(f"/dependents/{dep}/kyc-verify", json={"password": PASSWORD, "cnic": GOOD_CNIC})
    assert_error(r, 422, "VALIDATION_ERROR")


def test_cnic_ending_zero_fails_then_retry_succeeds(client, db):
    dep = new_dependent(client)
    failed = kyc(client, dep, cnic="42101-1234567-0").json()
    assert failed["status"] == "failed" and failed["next_step"] == "retry"
    assert db.get(DependentProfile, uuid.UUID(dep)).liveness_status == "failed"
    assert kyc(client, dep).json()["status"] == "verified"


def test_cnic_ending_nine_is_pending_then_verified_on_resubmission(client):
    dep = new_dependent(client)
    first = kyc(client, dep, cnic="42101-1234567-9").json()
    assert first["status"] == "pending" and first["next_step"] == "retry"
    assert kyc(client, dep, cnic="42101-1234567-9").json()["status"] == "verified"


def test_failed_liveness(client):
    dep = new_dependent(client)
    body = kyc(client, dep, photo="FAIL-blurry").json()
    assert body["status"] == "failed"


def test_wrong_password_unknown_id_and_guardian_id_look_identical(client):
    _, guardian_id = guardian_token(client)
    dep = new_dependent(client)
    wrong = kyc(client, dep, password="not-the-password")
    unknown = kyc(client, str(uuid.uuid4()))
    as_guardian = kyc(client, guardian_id)
    for r in (wrong, unknown, as_guardian):
        assert_error(r, 401, "INVALID_CREDENTIALS")
    assert wrong.json() == unknown.json() == as_guardian.json()


def test_already_verified_cannot_resubmit(client):
    dep = new_dependent(client)
    assert kyc(client, dep).status_code == 200
    assert_error(kyc(client, dep), 409, "ALREADY_VERIFIED")


def test_cnic_cannot_be_reused_by_another_dependent(client):
    d1 = new_dependent(client, 1)
    d2 = new_dependent(client, 2)
    assert kyc(client, d1).status_code == 200
    assert_error(kyc(client, d2), 409, "CNIC_ALREADY_REGISTERED")


def test_bad_uuid_in_path(client):
    assert_error(kyc(client, "not-a-uuid"), 422, "VALIDATION_ERROR")


# ------------------------------------------------------------- guardian KYC


def test_guardian_endpoints_need_a_token(client):
    assert_error(client.get("/guardians/me/verification"), 401, "NOT_AUTHENTICATED")
    assert_error(client.post("/guardians/me/verify-phone/request"), 401, "NOT_AUTHENTICATED")


def test_dependent_token_cannot_use_guardian_endpoints(client):
    dep = new_dependent(client)
    token = security.create_access_token(uuid.UUID(dep), "dependent")
    assert_error(client.get("/guardians/me/verification", headers=auth(token)), 403, "FORBIDDEN")


def test_new_guardian_starts_unverified(client):
    token, _ = guardian_token(client)
    body = client.get("/guardians/me/verification", headers=auth(token)).json()
    assert body == {"verified": False, "phone_verified": False, "cnic_verified": False, "status": None}


def test_guardian_phone_otp_flow(client, db):
    token, gid = guardian_token(client)
    req = client.post("/guardians/me/verify-phone/request", headers=auth(token))
    assert req.status_code == 200, req.text
    assert req.json()["sent"] is True and req.json()["expires_in"] == 300

    wrong = client.post("/guardians/me/verify-phone/confirm", json={"code": "000000"}, headers=auth(token))
    assert_error(wrong, 400, "OTP_INVALID")

    code = req.json()["dev_otp"]  # present because ENVIRONMENT=development in tests
    ok = client.post("/guardians/me/verify-phone/confirm", json={"code": code}, headers=auth(token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["verified"] is True and ok.json()["phone_verified"] is True
    db.expire_all()
    assert db.get(GuardianProfile, uuid.UUID(gid)).phone_verified is True


def test_guardian_cnic_verified(client):
    token, _ = guardian_token(client)
    r = client.post("/guardians/me/verify-cnic", json={"cnic": "4210112345671"}, headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["verified"] is True and r.json()["cnic_verified"] is True and r.json()["status"] == "verified"


def test_guardian_cnic_failed_stays_unverified(client):
    token, _ = guardian_token(client)
    r = client.post("/guardians/me/verify-cnic", json={"cnic": "42101-1234567-0"}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["verified"] is False and r.json()["status"] == "failed"


def test_guardian_cnic_validation(client):
    token, _ = guardian_token(client)
    r = client.post("/guardians/me/verify-cnic", json={"cnic": "nope"}, headers=auth(token))
    assert_error(r, 422, "VALIDATION_ERROR")


def test_require_verified_guardian_dependency(client):
    path = "/__test__/needs-verified-guardian"

    def _probe(user: User = Depends(require_verified_guardian)):
        return {"ok": True}

    app.add_api_route(path, _probe, methods=["GET"])
    try:
        token, _ = guardian_token(client)
        assert_error(client.get(path, headers=auth(token)), 403, "GUARDIAN_NOT_VERIFIED")
        client.post("/guardians/me/verify-cnic", json={"cnic": GOOD_CNIC}, headers=auth(token))
        assert client.get(path, headers=auth(token)).json() == {"ok": True}
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != path]
