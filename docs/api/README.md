# Humsafar API reference (Tasks 1.3 to 5.2)

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
| `alarm_contract.md` | Remote Alarm Override: Primary-only loud alarm on the Dependent's phone |
| `emergency_contact_contract.md` | External Emergency Contact: the ONE person outside the app, texted when no Guardian answers |
| `messaging_contract.md` | Text and priority voice messages between a Guardian and a Dependent: send, history, conversations, read receipts, safe retry, audio download |
| `call_contract.md` | Voice and video calls: start, ring, accept / decline / end, join token for ZegoCloud, history, timeouts |
| `booking_contract.md` | Home-care booking requests and the shared Activity Timeline (6.2) |
| `camera_contract.md` | Camera pairing, on-demand live viewing, permission gate (6.3) |
| `audit_contract.md` | Activity history / audit log, Primary Guardian only (6.6) |
| `directory_contract.md` | Healthcare directory and home-care provider directory: search, filters, nearby, details (6.1) |
| `wearable_contract.md` | Wearable band (mock data first): pair, sync readings, status, "no data" notice, demo data (5.4) |
| `vitals_contract.md` | Manual vitals (blood pressure, sugar, SpO2, temperature): save, list, latest, delete, separate / combined PDF (5.3) |
| `records_contract.md` | Medical Vault: records with files (encrypted), notes, PDF export (complete / year / month), doctor-shareable 72 h link, per-category access for a Secondary (5.2) |
| `appointment_contract.md` | Appointments: add / move / cancel, who is told, reminders 24 h and 1 h before |
| `../backend/sds_clarifications.md` | every place the SDS was silent or contradictory, with our decision |

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
| POST `/dependents/{id}/alarm` | **Primary Guardian only** (not delegable) | Sound the alarm on the Dependent's phone (10 to 300 s) |
| GET `/dependents/{id}/alarm` | The Primary, or the Dependent's phone | Is an alarm sounding? |
| POST `/dependents/{id}/alarm/stop` | The Primary, or the Dependent | Stop the alarm |
| PUT `/dependents/{id}/emergency-contact` | **Primary Guardian only** | Set / replace the ONE external emergency contact |
| GET `/dependents/{id}/emergency-contact` | The Primary, or a Secondary with `emergency_alerts` | Read it |
| DELETE `/dependents/{id}/emergency-contact` | **Primary Guardian only** | Remove it |
| PUT `/devices/push-token` | logged in | Register this phone's Firebase token |
| DELETE `/devices/push-token?token=` | logged in | Forget the token (logout) |
| GET `/health`, `/health/db` | anyone | Liveness checks |
| POST `/messages` | linked Guardian or Dependent (Secondary needs `communication`) | Send a text message (optional `client_id` for safe retry) |
| GET `/messages` | same | History with one person (newest first, paged) |
| GET `/messages/conversations` | same | My conversations, last message, unread count |
| POST `/messages/read` | same | Mark a person's messages as read |
| POST `/messages/voice` | Guardian (Secondary needs `communication`) | Send a priority voice message (multipart: `receiver_id`, `duration_s`, `audio`, optional `client_id`); critical notification |
| GET `/messages/{id}/audio` | sender or receiver | Download the audio of a voice message |
| POST `/calls` | linked Guardian or Dependent (Secondary needs `communication`) | Start a voice or video call (rings the other person) |
| GET `/calls` | me | Call history (newest first, paged) |
| GET `/calls/{id}` | caller or callee | State of a call (+ join info when allowed) |
| POST `/calls/{id}/accept` | callee | Accept (gets the join info) |
| POST `/calls/{id}/decline` | callee | Decline |
| POST `/calls/{id}/end` | caller or callee | Hang up / cancel |
| POST `/dependents/{id}/records` | the Dependent, or a Guardian with `health_records` | Add a medical record (multipart: `category`, `title`, `record_date`, optional `notes`, `client_id`, `file`) |
| GET `/dependents/{id}/records` | same | List records (filters `category`, `year`, `month`; `limit` / `offset`) |
| GET `/dependents/{id}/records/{record_id}` | same | One record |
| GET `/dependents/{id}/records/{record_id}/file` | same | Download the original file (stored encrypted) |
| PATCH / DELETE `/dependents/{id}/records/{record_id}` | uploader, or the Primary | Change / delete a record |
| GET `/dependents/{id}/records/export` | same as list | PDF export: `scope` = `complete` / `year` / `month`; `include_vitals=true` adds the vitals |
| POST / GET `/dependents/{id}/records/share` | same as list | Make a doctor link (default 72 h) / list the links |
| DELETE `/dependents/{id}/records/share/{share_id}` | link maker, Primary, Dependent | Cancel a link |
| GET `/dependents/{id}/records/access` | Primary | Which record categories each Secondary may see (5.2) |
| PUT `/dependents/{id}/records/access/{category}` | Primary | Show / hide one category for one Secondary (body `guardian_id`, `visible`) |
| GET `/dependents/{id}/records/access/me` | same as list | Which categories I may see |
| POST / GET `/dependents/{id}/vitals` | the Dependent, or a Guardian with `health_records` | Save / list manual vitals (5.3) |
| GET `/dependents/{id}/vitals/latest` | same | Newest reading of each metric |
| GET / DELETE `/dependents/{id}/vitals/{reading_id}` | same (delete: who typed it, or the Primary) | One / delete a reading |
| GET `/dependents/{id}/vitals/export` | same | Separate vitals PDF (`scope`, `year`, `month`) |
| POST / GET / DELETE `/dependents/{id}/wearable` | Dependent or Primary (GET: health-data readers) | Pair the band / band status / unpair (5.4) |
| POST `/dependents/{id}/wearable/sync` | the Dependent's own phone | Send a batch of band readings |
| POST `/dependents/{id}/wearable/mock` | Dependent or Primary | Demo: make fake heart-rate readings |
| GET `/directory/organizations` | any signed-in user | Healthcare directory: search (`q`), `type`, `city`, `open_24h`, nearby (`lat`+`lng`, `radius_km`), paging (6.1) |
| GET `/directory/organizations/types` / `/{org_id}` | same | Types with counts / one organization |
| GET `/directory/providers` | same | Home-care providers: `q`, `specialization`, `city`, `min_charge`, `max_charge`, `sort`, paging |
| GET `/directory/providers/specializations` / `/{provider_id}` | same | Specializations with counts / one provider |
| POST / GET `/dependents/{id}/bookings` | the Dependent, or a Guardian with `health_records` | Ask a listed provider for a visit / list requests (`status`) (6.2) |
| GET `/dependents/{id}/bookings/{request_id}` | same | One request |
| POST `/dependents/{id}/bookings/{request_id}/confirm` / `complete` / `cancel` | the person who asked, or the Primary | Change the request's status |
| POST `/dependents/{id}/directory/contacts` | the Dependent, or a Guardian with `health_records` | Log "contacting this organization" (the app then opens the dialer) |
| GET `/dependents/{id}/activity` | same | The unified Activity Timeline (`type`, `from`, `to`, paging) |
| POST / GET / DELETE `/dependents/{id}/camera` | pair: the Dependent or the Primary; status: the Dependent, the Primary, a Secondary with `camera_viewing` | Pair the camera phone / status / unpair (6.3) |
| POST `/dependents/{id}/camera/heartbeat` | the Dependent's own phone | "Is anyone watching?" The phone publishes only when `should_publish` |
| GET / DELETE `/dependents/{id}/camera/stream` | the Primary, or a Secondary with `camera_viewing` | Start or renew watching (returns the join token) / stop watching |
| GET `/dependents/{id}/camera/viewing` | the Dependent | Who is watching now (FR-K1.3 indicator) |
| POST `/dependents/{id}/camera/clips/{clip_id}` | the Dependent's own phone | Upload the emergency clip (MP4/WebM, 30 MB) asked for in the heartbeat (6.4) |
| GET `/dependents/{id}/camera/clips` / `/{clip_id}` | the Dependent, the Primary, a Secondary with `camera_viewing` | List clips (`status`, paging) / one clip |
| GET `/dependents/{id}/camera/clips/{clip_id}/video` | same | Download the decrypted video (Guardian downloads are audited) |
| DELETE `/dependents/{id}/camera/clips/{clip_id}` | the Dependent, the Primary | Delete a clip |
| GET `/shared/records/{token}` | **anyone with the link (no login)** | The doctor's read-only PDF |
| POST / GET `/dependents/{id}/appointments` | the Dependent, or a Guardian with `health_records` | Add / list appointments (`when` = `upcoming` / `past` / `all`) |
| GET / PATCH / DELETE `/dependents/{id}/appointments/{appointment_id}` | same | One / change / delete |
| POST `/dependents/{id}/appointments/{appointment_id}/cancel` | same | Cancel (kept in the history) |

Modules: `live_location`, `health_records`, `communication`, `emergency_alerts`, `camera_viewing`, `medication_management`.

## 4. Errors
Every error has the same shape; branch on `error.code`, never on `message`:
```json
{ "error": { "code": "GUARDIAN_NOT_VERIFIED", "message": "...", "details": {} } }
```
| Status | Codes |
|---|---|
| 400 | `CONFIRM_TOKEN_EXPIRED`, `CONFIRM_TOKEN_INVALID`, `INVITE_EXPIRED`, `INVITE_INVALID`, `OTP_INVALID`, `PRIMARY_NOT_GOVERNABLE` |
| 429 | `TOO_MANY_REQUESTS` (Task 6.5): too many wrong passwords for one email (8 in 5 minutes), too many wrong phone codes (5 in 5 minutes), or too many login / register calls from one address (60 per minute). `Retry-After` header and `details.retry_after_s` say how long to wait; show "try again in N seconds" |
| 400 | `HTTPS_REQUIRED` (only when the server runs with `ENFORCE_HTTPS=true`): use https |
| 401 | `NOT_AUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` (call refresh, retry once), `TOKEN_INVALID`, `TOKEN_WRONG_TYPE` |
| 403 | `RECORD_MODIFY_DENIED`, `SHARE_MODIFY_DENIED`, `CATEGORY_NOT_ALLOWED`, `ACCOUNT_NOT_ACTIVATED`, `FORBIDDEN`, `GUARDIAN_NOT_VERIFIED`, `INVITE_NOT_FOR_YOU`, `MODULE_ACCESS_DENIED`, `NOT_LINKED_TO_DEPENDENT`, `NOT_PRIMARY_GUARDIAN`, `PRIMARY_CANNOT_ACCEPT_INVITE`, `SECONDARY_CANNOT_LINK` |
| 404 | `RECORD_NOT_FOUND`, `NO_FILE`, `FILE_NOT_FOUND`, `SHARE_NOT_FOUND`, `APPOINTMENT_NOT_FOUND`, `NOT_FOUND`, `DEPENDENT_NOT_FOUND`, `DOSE_NOT_FOUND`, `EMERGENCY_CONTACT_NOT_FOUND`, `GEOFENCE_NOT_FOUND`, `MEDICATION_NOT_FOUND`, `NO_DOSE_DUE`, `NOTIFICATION_NOT_FOUND`, `SECONDARY_NOT_FOUND`, `ESCALATION_NOT_FOUND`, `WELLNESS_CHECK_NOT_FOUND` |
| 409 | `RECORDS_LIMIT`, `SHARE_LIMIT`, `APPOINTMENT_EXISTS`, `APPOINTMENTS_LIMIT`, `APPOINTMENT_CANCELLED`, `ALREADY_ESCALATED`, `ALREADY_LINKED`, `ALREADY_REGISTERED`, `ALREADY_VERIFIED`, `CNIC_ALREADY_REGISTERED`, `DOSE_ALREADY_CONFIRMED`, `EMAIL_ALREADY_REGISTERED`, `GEOFENCE_LIMIT_REACHED`, `GUARDIAN_CAP_REACHED`, `INVITEE_NOT_ELIGIBLE`, `MEDICATION_LIMIT_REACHED`, `NO_ACTIVE_ALARM`, `NO_ACTIVE_PANIC`, `NO_OPEN_ALERT`, `SCHEDULE_ALREADY_EXISTS`, `WELLNESS_LIMIT_REACHED`, `WELLNESS_TIME_EXISTS`, `PHONE_ALREADY_REGISTERED`, `PRIMARY_ALREADY_EXISTS` |
| 410 | `SHARE_EXPIRED`, `SHARE_REVOKED` (the doctor link) |
| 413 / 415 | `FILE_TOO_LARGE` / `UNSUPPORTED_FILE` (record files: PDF, JPEG, PNG up to 10 MB) |
| 422 | `RECORD_NEEDS_CONTENT`, `INVALID_DATE`, `APPOINTMENT_IN_PAST`, `VALIDATION_ERROR` (`details.fields` lists each bad field), `UNKNOWN_MODULE`, `TIMESTAMP_IN_FUTURE`, `TIMESTAMP_TOO_OLD`, `INVALID_RANGE` |
| 500 | `INTERNAL_ERROR`, `FILE_UNREADABLE` (a stored record file is damaged) |

## 5. The user journey (what the screens follow)
1. **Guardian:** register, log in, verify (CNIC or phone OTP).
2. **Dependent:** register, submit KYC. They cannot log in yet (`ACCOUNT_NOT_ACTIVATED`).
3. **Guardian** links the Dependent (needs the Dependent's `user_id`). The Dependent can now log in.
4. **Primary** invites up to two Secondaries by phone; each registers with the `invite_token`.
5. **Primary** switches modules on for each Secondary on the permission screen. Secondaries start with nothing.

## 6. Mock behaviour you will notice
- KYC and OTP are mocked. A CNIC ending in `0` fails, ending in `9` stays pending, any other ending passes. A liveness photo starting with `FAIL` fails. In development, `verify-phone/request` returns the code as `dev_otp`.
- `full_name` is required at register and returned in every `user` object (clarification item 27).
