# KYC API Contract (Task 1.4, mocked provider)

Status: implemented on branch `feature/1.4-kyc-endpoints`. Owner: Abdullah (backend). Consumers: Talha (KYC capture screens), Sarim (QA).
Errors use the standard envelope from `auth_contract.md` section 1. Branch on `error.code`.

The verification provider is a **mock** (SDS 3.3 specifies a third-party provider; none is chosen yet). Its results are deterministic so every outcome can be demoed and tested, see section 4.

## 1. Dependent KYC (FR-A2)

### POST /dependents/{id}/kyc-verify  → 200
`{id}` is the Dependent's `user_id` from `/auth/register`.

**No JWT.** An un-activated Dependent cannot log in (SDS 11.3), so they have no token. They prove who they are with their password in the body.

Request:
```json
{ "password": "their-account-password", "cnic": "42101-1234567-1", "liveness_image": "<base64 photo>" }
```
- `cnic`: 13 digits, with or without dashes. Stored as `12345-1234567-1`. First digit cannot be 0.
- `liveness_image`: base64 text of the live photo (max about 2 MB). It is checked and discarded; the SDS has no column to store it.

Response 200:
```json
{ "status": "verified", "message": "Verified. Your account activates once your Primary Guardian links you.",
  "account_active": false, "next_step": "link_primary_guardian" }
```
- `status`: `verified` | `pending` | `failed`.
- `next_step`: `link_primary_guardian` (verified, waiting for a Primary), `none` (verified and active, they can log in now), `retry` (pending or failed: submit again).
- A Dependent can log in only when `verified` AND linked to an active Primary Guardian (Task 1.5).

Errors: 401 `INVALID_CREDENTIALS` (wrong password, unknown id, or id of a non-Dependent: all identical), 409 `ALREADY_VERIFIED`, 409 `CNIC_ALREADY_REGISTERED` (CNIC belongs to another account), 422 `VALIDATION_ERROR`.

## 2. Guardian verification (FR-A3)
All need `Authorization: Bearer <access_token>` of a Guardian. A Guardian is **verified** when the phone OTP **or** the CNIC check has passed. Guardians can log in and call these before being verified. Features that need a verified Guardian (permission dashboard, interventions, from Tasks 1.5/1.6) return **403 `GUARDIAN_NOT_VERIFIED`** until then.

| Endpoint | Purpose |
|---|---|
| `GET /guardians/me/verification` | `{ "verified", "phone_verified", "cnic_verified", "status": null }` |
| `POST /guardians/me/verify-phone/request` | Sends an OTP. Returns `{ "sent": true, "expires_in": 300, "dev_otp": "123456" }`. `dev_otp` appears only in development. |
| `POST /guardians/me/verify-phone/confirm` | Body `{ "code": "123456" }`. Same response shape as status. 400 `OTP_INVALID` if wrong. |
| `POST /guardians/me/verify-cnic` | Body `{ "cnic": "42101-1234567-1" }`. Returns status with `"status": "verified" | "failed"`. |

Other errors: 401 `NOT_AUTHENTICATED` / token errors, 403 `FORBIDDEN` (not a Guardian), 422 `VALIDATION_ERROR`.
No liveness photo for Guardians (FR-A3). The Guardian's CNIC number is not stored, only the pass/fail result.

## 3. Suggested client flow
- **Dependent app:** register, then capture CNIC + liveness, call kyc-verify. `verified` + `link_primary_guardian` shows a "waiting for your guardian" screen. `retry` lets them resubmit. Once linked, login works.
- **Guardian app:** after login, call `/guardians/me/verification`. If not verified, show the OTP screen (request, then confirm) or the CNIC screen.

## 4. Mock rules (for demos and QA)
| Input | Result |
|---|---|
| CNIC ending in **0** | `failed` |
| CNIC ending in **9** | Dependent: `pending` first time, `verified` when the same CNIC is submitted again. Guardian: `verified`. |
| Any other CNIC | `verified` |
| `liveness_image` starting with `FAIL` | `failed` |
| OTP | always `123456` (configurable via `MOCK_OTP_CODE`) |

## 5. Added or deviating (flagged)
- `POST /dependents/{id}/kyc-verify` is the SDS 11.1 endpoint, but the SDS marks it "JWT" while 11.3 says Dependents get no token before verification. We authenticate by password in the body. See `docs/sds_clarifications.md`.
- All `/guardians/me/*` endpoints are additions; the SDS lists no Guardian verification endpoint.
- Rate limiting on these endpoints (SDS 17) is deferred to hardening.
