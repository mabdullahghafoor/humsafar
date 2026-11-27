# Humsafar Progress Tracker

Maintained by Abdullah; updated at the end of every backend task. Last updated: 2026-11-27 (statuses brought up to date by Sarim from the team tracker; Abdullah to confirm).
Statuses: Done = merged into `dev`.

## Backend (Abdullah)
| Task | What | Status |
|---|---|---|
| 0.1 to 0.3 | Repo, FastAPI skeleton, PostgreSQL + SQLAlchemy | Done |
| 0.5 | Postman workspace + base collection | Done |
| 1.1 | SQLAlchemy models, all 27 tables | Done |
| 1.2 | Alembic initial migration | Done |
| 1.3 | Auth: register, login, refresh, me (+ contract `docs/api/auth_contract.md`) | Done |
| 1.4 | KYC endpoints, mocked provider (+ contract `docs/api/kyc_contract.md`) | Done |
| 1.5 | Guardian-Dependent linkage + caps, invitations (+ contract `docs/api/linkage_contract.md`) | Done |
| 1.6 | Permission dashboard + access gate (+ contract `docs/api/permissions_contract.md`) | Done |
| 1.7 | One consolidated Postman collection with examples + API index (`docs/api/README.md`) | Done |
| ICP-1 | Register, KYC, link, permissions: run 26 to 29 Oct on real phones, 22 / 23 steps passed, signed off (`docs/qa/results/debug-apk-1.7/`) | Done |
| 2.1 | Location ingestion + adaptive frequency, latest + history (+ contract `docs/api/location_contract.md`) | Done |
| 2.2 | Geofence CRUD (max 10 zones) + breach detection (+ contract `docs/api/geofence_contract.md`) | Done |
| 2.3 | Battery alert (15%), offline detection (10 min), device-health read, background job runner (+ contract `docs/api/device_health_contract.md`) | Done |
| 2.5-prep | `users.full_name` (migration 0002) + guide `docs/backend/RUNNING_THE_BACKEND.md` for Talha | Done |
| 3.1 | Notification service: critical / standard tiers, inbox, acknowledgment, push tokens, mock push (+ contract `docs/api/notification_contract.md`) | Done |
| 3.2 | Medication schedules, reminders (standard before, critical at dose time), two-step dose confirmation (+ contract `docs/api/medication_contract.md`) | Done |
| 3.3 | Missed-dose detection, critical alert to the Primary, Guardian options: extend time or escalate to Secondaries, late confirmation closes the alert (section in `medication_contract.md`) | Done |
| 3.4 | Guardian wellness check: up to 3 daily "Are you OK?" prompts, grace period, device-activity cross-check, alert to the Primary if unanswered (+ contract `docs/api/wellness_contract.md`) | Done |
| 3.5 | Escalation chain: Primary, then Secondary, then external-contact level, by timers; Guardian acknowledge stops it (+ contract `docs/api/escalation_contract.md`) | Done |
| 3.6 | Panic Mode: Dependent button tells every linked Guardian at once, permissions ignored; one open panic at a time; close by Dependent or Primary (+ contract `docs/api/panic_contract.md`) | Done |
| 3.7 | Remote Alarm Override: Primary Guardian only, loud alarm on the Dependent's phone, start / status / stop (+ contract `docs/api/alarm_contract.md`) | Done |
| 3.8 | External Emergency Contact fallback: ONE contact per Dependent, mock SMS when an alert reaches the last escalation level, retries, all-clear (+ contract `docs/api/emergency_contact_contract.md`) | Done |
| 4.1 | Call technology decision: hosted SDK, ZegoCloud (clarification 75) | Done |
| 4.2 | Text messaging: send, history, conversations, read receipts, safe retry, permission `communication` (+ contract `docs/api/messaging_contract.md`) | Done |
| 4.3 | Priority voice messages: Guardian uploads audio, critical notification, download, safe retry (section in `messaging_contract.md`) | Done |
| 4.4 | Voice / video calls: start, ring, accept / decline / end, join token (mock provider), timeouts, history (+ contract `docs/api/call_contract.md`) | Done |
| 4.4b | Real ZegoCloud join token (token04) behind `CALL_PROVIDER=zego`; keys only in `.env` (PR #41; checked live with the real keys) | Done |
| 5.1 | Medical vault (records + encrypted files, PDF export complete / year / month, 72 h doctor link) and appointments with reminders (migration 0012; contracts `records_contract.md`, `appointment_contract.md`) | Done (PR #47) |
| 5.2 | Field-level access on records: the Primary hides single record categories from a Secondary, per Dependent (migration 0013; section in `records_contract.md`) | Done (PR #51) |
| 5.3 | Manual vitals (blood pressure, sugar, SpO2, temperature): save, list, latest, delete, unit conversion, separate or combined PDF, doctor link can include vitals (migration 0014; contract `vitals_contract.md`) | Done (PR #58) |
| 5.4 | Wearable band with mock data: pair / unpair, sync of heart rate (+ SpO2, temperature), status, "no data" detection with a standard notification, demo-data endpoint, daily band summary in the PDFs (migration 0015; contract `wearable_contract.md`) | Done (PR #59) |
| 5.5 | Real wearable band integration | **In progress**: the band is ready and with Abdullah; the app side (Bluetooth scan, live readings, sync) was built by Talha on 26 Nov against the 9-byte packet spec and is not yet tested on the real band |
| 6.1 | Healthcare directory (hospitals, ambulances, pharmacies...) and home-care provider directory: list, search, filters, "nearby", details, starting content (migration 0016; contract `directory_contract.md`) | Done (PR #60) |
| 6.2 | Home-care booking requests (pending, confirmed, completed, cancelled) and the shared Activity Timeline for organization contacts and bookings (migration 0017; contract `booking_contract.md`) | Done (PR #67) |
| 6.3 | Camera pairing and live viewing: spare phone in camera mode publishes into a private video room only while a Guardian watches; Primary always, Secondary needs `camera_viewing`; viewing sessions with renewal, viewer limit, "being viewed" indicator and notices (migration 0018; contract `camera_contract.md`) | Done (PR #70) |
| 6.4 | Event-triggered clip capture: Panic Mode or Remote Alarm asks the camera phone to record a short clip; upload, encrypted storage, list, download (audited), delete (migration 0019; contract `camera_contract.md`) | Done (PR #72) |
| 6.5 | Encryption and transport formalization: https-only option, HSTS and security headers, production start-up checks, rate limits on login / OTP / KYC (SDS 17), encryption audit script and data inventory (`docs/backend/security_encryption.md`) | Done (PR #73) |
| 6.6 | Audit log reading (FR-N3): every audit row now names its Dependent (migration 0020, old rows filled in); `GET /dependents/{id}/audit-log` for the Primary Guardian only, newest first, filters and paging (contract `audit_contract.md`) | Done (PR #74) |
| 6.7 | Data retention job (FR-O1): a Guardian closes their account, the Primary closes a Dependent's; closed accounts stop working at once and the background job deletes / anonymizes the data after 60 days (audit trail kept 365 days longer, hold flag for disputes), reopen within the period (migration 0021; contract `account_contract.md`, guide `data_retention.md`) | Done (PR #75) |
| 7.1 | Analytics aggregation (FR-Q1): adherence rate, per-day and per-medicine, change against the previous period, streak; vitals min / max / average / latest / daily / trend for blood pressure, sugar, SpO2, temperature, heart rate (manual and band together); Guardians only, by permission; one combined call for the dashboard (no migration; contract `analytics_contract.md`) | Done (PR #76) |
| 7.2 | Summary reports (FR-Q2): a Guardian switches a weekly or monthly report on per Dependent; the background job makes the PDF of the last finished week / month (adherence + vitals trends from 7.1, only the parts the Guardian may see), stores it encrypted and sends a notification; make-one-now, list, download, delete; reports are deleted with the account (migration 0022; contract `reports_contract.md`) | Done (PR #77) |
| 2.4 | BLE integration spike | **Open, parked**: needs a real Android phone (planned at a teammate's home with the camera-phone setup, 6.10) |

## Frontend (Talha) — kept in his own repo `humsafar-talha-frontend`
The Flutter app is built in Talha's repo and handed out as debug APKs (latest tested: `debug-apk-1.9.5`, 26 Nov). All screens up to Phase 7 are built; open app findings (incoming calls, alarm on a locked phone, duplicate notices, signed release build) are in `docs/qa/results/debug-apk-1.9.5/`. Talha's own tracker is the source for task status. The frontend folder is folded into `frontend/` here at each Integration Checkpoint.

## Design / QA / Docs (Sarim)
Tracked in the team's shared tracker. Designs are in `docs/design/`, test cases and results (one folder per APK build, security results kept separately) in `docs/qa/`, drift register and design history in `docs/reports/`.

## Waiting for hardware or a physical Android phone
Kept up to date by Abdullah; reminded as soon as the hardware or an Android phone is available.
| Item | Needs | Blocks |
|---|---|---|
| 2.4 BLE integration spike | A real Android phone (done together with 6.10 at a teammate's home) | 5.5 and the ICP-2 review |
| 5.5 Real band integration | The band, the spike 2.4, the chip name, an nRF Connect Bluetooth test, the source code and the sensor list from the supplier (clarifications 88, 89) | Live band data; switch `WEARABLE_MOCK_ENABLED=false` afterwards |
| Step count (FR-H2) | The sensor list (clarification 89) | Nothing else |
| 6.10 Spare phone in camera mode | A second Android phone (with Talha) | Live camera view demo (ICP-6) |
| Real ZegoCloud call test on two phones | A fix for the incoming-call screen (finding F-29, Talha) | Voice / video calls in ICP-4 |

## Open decisions and blockers
See `docs/backend/sds_clarifications.md`. Real push works (checked on real phones, 9 Nov). The hosted server runs on Render in staging mode with mock phone codes and a free database that ends on 24 Dec 2026, so a plan is needed after that date. Currently open: SDS 11.1/11.3 KYC auth and Guardian OTP timing (team confirmation), Dependent consent when a Guardian links (item 9), no way to remove a Guardian (item 12).
