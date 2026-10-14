# Humsafar Progress Tracker

Maintained by Abdullah's Claude session; updated at the end of every backend task. Last updated: 2026-10-14.
Statuses: Done = merged into `dev`.

## Backend (Abdullah)
| Task | What | Status |
|---|---|---|
| 0.1 to 0.3 | Repo, FastAPI skeleton, PostgreSQL + SQLAlchemy | Done |
| 0.5 | Postman workspace + base collection | Done |
| 1.1 | SQLAlchemy models, all 27 tables | Done |
| 1.2 | Alembic initial migration | Done |
| 1.3 | Auth: register, login, refresh, me (+ contract `docs/api/auth_contract.md`) | Done |
| 1.4 | KYC endpoints, mocked provider (+ contract `docs/api/kyc_contract.md`) | In progress |
| 1.5 | Guardian-Dependent linkage + caps | Next |
| 1.6 | Permission dashboard | Planned |
| 1.7 | Postman collection for 1.3 to 1.6 | Planned |
| ICP-1 | Register, KYC, link, permissions demo with Talha and Sarim | Planned |

## Frontend (Talha) — kept in his own repo `humsafar-talha-frontend`
Last known from his tracker (2026-08-12): Tasks 0.4 and 1.8 to 1.11 done in his repo. Talha: please keep this section current. The frontend folder is folded into `frontend/` here at each Integration Checkpoint.

## Design / QA / Docs (Sarim)
Not tracked in this file yet. Sarim: please add your task status here.

## Open decisions and blockers
See `docs/sds_clarifications.md`. Currently open: `users.full_name` (Talha + Abdullah), SDS 11.1/11.3 KYC auth and Guardian OTP timing (team confirmation).
