# Humsafar Progress Tracker

Maintained by Abdullah's Claude session; updated at the end of every backend task. Last updated: 2026-10-19.
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
| ICP-1 | Register, KYC, link, permissions: handled asynchronously (no live demo); waiting for Talha and Sarim replies | In progress |
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
| 4.2 | Text messaging: send, history, conversations, read receipts, safe retry, permission `communication` (+ contract `docs/api/messaging_contract.md`) | In review (PR) |
| 2.4 | BLE integration spike | **Open, parked**: needs a real Android phone (planned at a teammate's home with the camera-phone setup, 6.10) |

## Frontend (Talha) — kept in his own repo `humsafar-talha-frontend`
Last known from his tracker (2026-08-12): Tasks 0.4 and 1.8 to 1.11 done in his repo. Talha: please keep this section current. The frontend folder is folded into `frontend/` here at each Integration Checkpoint.

## Design / QA / Docs (Sarim)
Not tracked in this file yet. Sarim: please add your task status here.

## Open decisions and blockers
See `docs/backend/sds_clarifications.md`. Currently open: Firebase project for real push (Talha, Task 3.14, item 29), SDS 11.1/11.3 KYC auth and Guardian OTP timing (team confirmation), Dependent consent when a Guardian links (item 9), no way to remove a Guardian (item 12).
