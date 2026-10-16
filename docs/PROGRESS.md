# Humsafar Progress Tracker

Maintained by Abdullah's Claude session; updated at the end of every backend task. Last updated: 2026-10-15.
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
| 2.5-prep | `users.full_name` (migration 0002) + guide `docs/RUNNING_THE_BACKEND.md` for Talha | Done |
| 3.1 | Notification service: critical / standard tiers, inbox, acknowledgment, push tokens, mock push (+ contract `docs/api/notification_contract.md`) | In review (PR) |
| 2.4 | BLE integration spike | **Open, parked**: needs a real Android phone (planned at a teammate's home with the camera-phone setup, 6.10) |

## Frontend (Talha) — kept in his own repo `humsafar-talha-frontend`
Last known from his tracker (2026-08-12): Tasks 0.4 and 1.8 to 1.11 done in his repo. Talha: please keep this section current. The frontend folder is folded into `frontend/` here at each Integration Checkpoint.

## Design / QA / Docs (Sarim)
Not tracked in this file yet. Sarim: please add your task status here.

## Open decisions and blockers
See `docs/sds_clarifications.md`. Currently open: Firebase project for real push (Talha, Task 3.14, item 29), SDS 11.1/11.3 KYC auth and Guardian OTP timing (team confirmation), Dependent consent when a Guardian links (item 9), no way to remove a Guardian (item 12).
