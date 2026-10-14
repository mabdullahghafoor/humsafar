# Humsafar API - Phase 1 reference (Tasks 1.3 to 1.6)

For Talha (Flutter) and Sarim (QA). Base URL (local): `http://127.0.0.1:8000`. Interactive docs: `http://127.0.0.1:8000/docs`.
All bodies are JSON. The server is Abdullah's `backend/`.

## 1. Try it in two minutes
1. Start the backend: `uvicorn app.main:app --reload` (from `backend/`).
2. In Postman import `backend/postman/Humsafar_API_Phase1.postman_collection.json` and `backend/postman/Humsafar_Local.postman_environment.json`, then select **Humsafar Local**.
3. Run the whole collection (Collection Runner), or one folder. Each folder creates its own test accounts, so any order works. Every request has a description and a saved example response.

## 2. Contracts (details, field lists, flows)
| File | Covers |
|---|---|
| `auth_contract.md` | register, login, refresh, me, tokens, client flow |
| `kyc_contract.md` | Guardian verification, Dependent KYC |
| `linkage_contract.md` | link, invite, accept, caps, lists |
| `permissions_contract.md` | dashboard, grant/revoke, the access gate |
| `../sds_clarifications.md` | every place the SDS was silent or contradictory, with our decision |

## 3. All endpoints
| Method and path | Who | Purpose |
|---|---|---|
| POST `/auth/register` | anyone | Create a Guardian or Dependent (`invite_token` makes a Secondary) |
| POST `/auth/login` | anyone | Access (15 min) and refresh (7 days) tokens |
| POST `/auth/refresh` | anyone | New token pair from a refresh token |
| GET `/auth/me` | logged in | Current user |
| GET `/guardians/me/verification` | Guardian | Verification status |
| POST `/guardians/me/verify-phone/request` | Guardian | Send phone OTP (mocked) |
| POST `/guardians/me/verify-phone/confirm` | Guardian | Confirm OTP |
| POST `/guardians/me/verify-cnic` | Guardian | Verify by CNIC (mocked) |
| POST `/dependents/{id}/kyc-verify` | Dependent (password in body) | CNIC + liveness (mocked) |
| POST `/dependents/{id}/link` | verified Primary | Link to a Dependent |
| POST `/dependents/{id}/guardians/invite` | verified Primary | Invite a Secondary by phone |
| POST `/invitations/accept` | Secondary | Accept another invitation |
| GET `/guardians/me/dependents` | Guardian | My Dependents (switcher) |
| GET `/dependents/{id}/guardians` | linked Guardian | Who is linked |
| GET `/dependents/{id}/permissions` | verified Primary | Permission dashboard |
| GET `/dependents/{id}/permissions/me` | Guardian | My access for this Dependent |
| PUT `/dependents/{id}/permissions/{module}` | verified Primary | Grant or revoke one module |
| GET `/health`, `/health/db` | anyone | Liveness checks |

Modules: `live_location`, `health_records`, `communication`, `emergency_alerts`, `camera_viewing`, `medication_management`.

## 4. Errors
Every error has the same shape; branch on `error.code`, never on `message`:
```json
{ "error": { "code": "GUARDIAN_NOT_VERIFIED", "message": "...", "details": {} } }
```
| Status | Codes |
|---|---|
| 400 | `INVITE_EXPIRED`, `INVITE_INVALID`, `OTP_INVALID`, `PRIMARY_NOT_GOVERNABLE` |
| 401 | `NOT_AUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` (call refresh, retry once), `TOKEN_INVALID`, `TOKEN_WRONG_TYPE` |
| 403 | `ACCOUNT_NOT_ACTIVATED`, `FORBIDDEN`, `GUARDIAN_NOT_VERIFIED`, `INVITE_NOT_FOR_YOU`, `MODULE_ACCESS_DENIED`, `NOT_LINKED_TO_DEPENDENT`, `NOT_PRIMARY_GUARDIAN`, `PRIMARY_CANNOT_ACCEPT_INVITE`, `SECONDARY_CANNOT_LINK` |
| 404 | `NOT_FOUND`, `DEPENDENT_NOT_FOUND`, `SECONDARY_NOT_FOUND` |
| 409 | `ALREADY_LINKED`, `ALREADY_REGISTERED`, `ALREADY_VERIFIED`, `CNIC_ALREADY_REGISTERED`, `EMAIL_ALREADY_REGISTERED`, `GUARDIAN_CAP_REACHED`, `INVITEE_NOT_ELIGIBLE`, `PHONE_ALREADY_REGISTERED`, `PRIMARY_ALREADY_EXISTS` |
| 422 | `VALIDATION_ERROR` (`details.fields` lists each bad field), `UNKNOWN_MODULE` |
| 500 | `INTERNAL_ERROR` |

## 5. The user journey (what the screens follow)
1. **Guardian:** register, log in, verify (CNIC or phone OTP).
2. **Dependent:** register, submit KYC. They cannot log in yet (`ACCOUNT_NOT_ACTIVATED`).
3. **Guardian** links the Dependent (needs the Dependent's `user_id`). The Dependent can now log in.
4. **Primary** invites up to two Secondaries by phone; each registers with the `invite_token`.
5. **Primary** switches modules on for each Secondary on the permission screen. Secondaries start with nothing.

## 6. Mock behaviour you will notice
- KYC and OTP are mocked. A CNIC ending in `0` fails, ending in `9` stays pending, any other ending passes. A liveness photo starting with `FAIL` fails. In development, `verify-phone/request` returns the code as `dev_otp`.
- There is no `full_name` anywhere yet (open decision, `sds_clarifications.md`).
