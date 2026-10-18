# Humsafar API reference (Tasks 1.3 to 2.3)

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
| `location_contract.md` | location ingestion, adaptive interval, latest and history |
| `geofence_contract.md` | safe zones, breach detection, status |
| `device_health_contract.md` | battery alert, offline detection, device-health read |
| `notification_contract.md` | alerts (critical / standard), acknowledgment, push tokens |
| `medication_contract.md` | medicine schedules, reminders, two-step dose confirmation |
| `wellness_contract.md` | wellness check schedule, "Are you OK?" prompt, answer, unanswered-check alert |
| `escalation_contract.md` | the escalation chain: Primary, Secondary, external contact; timers; acknowledge |
| `panic_contract.md` | Panic Mode: the big button, who is told, closing it |
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
| POST `/dependents/{id}/location` | the Dependent (own token) | Send a GPS fix; reply says how long to wait for the next one |
| GET `/dependents/{id}/location` | Primary, or Secondary with `live_location` | Latest position |
| GET `/dependents/{id}/location/history` | Primary, or Secondary with `live_location` | Past positions (newest first) |
| POST `/dependents/{id}/geofences` | verified Primary | Create a safe zone (max 10) |
| GET `/dependents/{id}/geofences` | Primary, or Secondary with `live_location` | List zones |
| PUT `/dependents/{id}/geofences/{geofence_id}` | verified Primary | Change a zone |
| DELETE `/dependents/{id}/geofences/{geofence_id}` | verified Primary | Remove a zone |
| GET `/dependents/{id}/geofence-status` | Primary, or Secondary with `live_location` | Inside / outside + open breach |
| GET `/dependents/{id}/device-health` | Primary, or Secondary with `live_location` | Battery, online/offline, last known location |
| GET `/notifications` | logged in | My alerts (critical / standard), unacknowledged count, paging |
| POST `/notifications/{id}/acknowledge` | logged in (owner) | Acknowledge an alert (idempotent) |
| POST / GET `/dependents/{id}/medications` | Guardian with `medication_management` (GET: or the Dependent) | Create / list medicine schedules |
| PUT / DELETE `/dependents/{id}/medications/{schedule_id}` | Guardian with `medication_management` | Change / switch off a schedule |
| GET `/dependents/{id}/medication-doses` | Guardian with `medication_management`, or the Dependent | Dose history and upcoming doses |
| POST `/dependents/{id}/medication-doses/{confirmation_id}/extend` | Guardian with `medication_management` | Missed dose: give more time (5 to 120 min) |
| POST `/dependents/{id}/medication-doses/{confirmation_id}/escalate` | Guardian with `medication_management` | Missed dose: alert the Secondary Guardians now |
| POST `/medications/{schedule_id}/confirm-request` | Dependent | Step 1 of the two-step dose confirmation |
| POST `/medications/{schedule_id}/confirm` | Dependent | Step 2: mark the dose taken |
| POST `/dependents/{id}/wellness-checks` | Primary, or Secondary with `emergency_alerts` | Add 1 to 3 daily check times (grace 5 to 180 min) |
| POST `/dependents/{id}/wellness-checks/default-schedule` | same | Add 08:00, 14:00, 20:00 (only if none exist) |
| GET `/dependents/{id}/wellness-checks` | same, or the Dependent | List the checks |
| PUT / DELETE `/dependents/{id}/wellness-checks/{wc_id}` | same | Change / switch off a check |
| GET `/dependents/{id}/wellness-check-responses` | same, or the Dependent | History: pending, responded, device_active, escalated, cancelled |
| POST `/wellness-checks/{response_id}/respond` | Dependent | "I am OK" (safe to repeat) |
| GET `/dependents/{id}/escalations` | Primary, or Secondary with `emergency_alerts` | Alerts and where they are in the chain |
| POST `/escalations/{event_id}/acknowledge` | A Guardian who was told | "I have seen it": stops the escalation timer |
| POST `/dependents/{id}/panic` | The Dependent themself | Panic button: tells EVERY linked Guardian, permissions ignored |
| GET `/dependents/{id}/panic` | The Dependent, or any linked Guardian | Is a panic open? |
| POST `/dependents/{id}/panic/resolve` | The Dependent, or the Primary Guardian | Close the panic ("I am safe" / handled) |
| PUT `/devices/push-token` | logged in | Register this phone's Firebase token |
| DELETE `/devices/push-token?token=` | logged in | Forget the token (logout) |
| GET `/health`, `/health/db` | anyone | Liveness checks |

Modules: `live_location`, `health_records`, `communication`, `emergency_alerts`, `camera_viewing`, `medication_management`.

## 4. Errors
Every error has the same shape; branch on `error.code`, never on `message`:
```json
{ "error": { "code": "GUARDIAN_NOT_VERIFIED", "message": "...", "details": {} } }
```
| Status | Codes |
|---|---|
| 400 | `CONFIRM_TOKEN_EXPIRED`, `CONFIRM_TOKEN_INVALID`, `INVITE_EXPIRED`, `INVITE_INVALID`, `OTP_INVALID`, `PRIMARY_NOT_GOVERNABLE` |
| 401 | `NOT_AUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` (call refresh, retry once), `TOKEN_INVALID`, `TOKEN_WRONG_TYPE` |
| 403 | `ACCOUNT_NOT_ACTIVATED`, `FORBIDDEN`, `GUARDIAN_NOT_VERIFIED`, `INVITE_NOT_FOR_YOU`, `MODULE_ACCESS_DENIED`, `NOT_LINKED_TO_DEPENDENT`, `NOT_PRIMARY_GUARDIAN`, `PRIMARY_CANNOT_ACCEPT_INVITE`, `SECONDARY_CANNOT_LINK` |
| 404 | `NOT_FOUND`, `DEPENDENT_NOT_FOUND`, `DOSE_NOT_FOUND`, `GEOFENCE_NOT_FOUND`, `MEDICATION_NOT_FOUND`, `NO_DOSE_DUE`, `NOTIFICATION_NOT_FOUND`, `SECONDARY_NOT_FOUND`, `ESCALATION_NOT_FOUND`, `WELLNESS_CHECK_NOT_FOUND` |
| 409 | `ALREADY_ESCALATED`, `ALREADY_LINKED`, `ALREADY_REGISTERED`, `ALREADY_VERIFIED`, `CNIC_ALREADY_REGISTERED`, `DOSE_ALREADY_CONFIRMED`, `EMAIL_ALREADY_REGISTERED`, `GEOFENCE_LIMIT_REACHED`, `GUARDIAN_CAP_REACHED`, `INVITEE_NOT_ELIGIBLE`, `MEDICATION_LIMIT_REACHED`, `NO_ACTIVE_PANIC`, `NO_OPEN_ALERT`, `SCHEDULE_ALREADY_EXISTS`, `WELLNESS_LIMIT_REACHED`, `WELLNESS_TIME_EXISTS`, `PHONE_ALREADY_REGISTERED`, `PRIMARY_ALREADY_EXISTS` |
| 422 | `VALIDATION_ERROR` (`details.fields` lists each bad field), `UNKNOWN_MODULE`, `TIMESTAMP_IN_FUTURE`, `TIMESTAMP_TOO_OLD`, `INVALID_RANGE` |
| 500 | `INTERNAL_ERROR` |

## 5. The user journey (what the screens follow)
1. **Guardian:** register, log in, verify (CNIC or phone OTP).
2. **Dependent:** register, submit KYC. They cannot log in yet (`ACCOUNT_NOT_ACTIVATED`).
3. **Guardian** links the Dependent (needs the Dependent's `user_id`). The Dependent can now log in.
4. **Primary** invites up to two Secondaries by phone; each registers with the `invite_token`.
5. **Primary** switches modules on for each Secondary on the permission screen. Secondaries start with nothing.

## 6. Mock behaviour you will notice
- KYC and OTP are mocked. A CNIC ending in `0` fails, ending in `9` stays pending, any other ending passes. A liveness photo starting with `FAIL` fails. In development, `verify-phone/request` returns the code as `dev_otp`.
- `full_name` is required at register and returned in every `user` object (clarification item 27).
