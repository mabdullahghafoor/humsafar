# Data retention (Task 6.7, FR-O1)

**Rule:** data is kept while the account is active. When an account is closed, the data is deleted or anonymized `RETENTION_DAYS` later (default 60).

## How it works
1. `POST /account/close` or `POST /dependents/{id}/close` sets `users.closed_at` and `users.delete_after`.
2. The background job `retention_sweep` (`app/services/retention_service.py`, registered in `main.py`, runs with the other jobs when `SCHEDULER_ENABLED=true`) handles every account whose `delete_after` has passed, up to `RETENTION_BATCH` (50) per run, one transaction per account.
3. Reopening before that clears `delete_after`; the job never touches a reopened account (it re-checks under a row lock).

## What happens to what
| Data | At deletion |
|---|---|
| Dependent: location, vitals and band readings, medical records and their files, camera clips and their files, messages and voice files, call history, medication and wellness schedules and answers, appointments, booking requests, activity timeline, geofences, emergency contact, wearable and camera pairings, alerts, notifications about them, push tokens, links, permissions, doctor links | **deleted** (files removed from disk after the commit) |
| The Dependent's identity (name, email, phone, ID number, birth date, notes) | **anonymized** ("Deleted user", `deleted-<random>@deleted.invalid`, password unusable) |
| Guardian | personal details **anonymized**; links, permissions, notifications, push tokens deleted. Messages and calls with a Dependent who stays are kept, shown as from "Deleted user" |
| Audit trail (FR-N3) | **kept** `AUDIT_RETENTION_DAYS` (365) after the deletion, then removed. It holds ids, action names and times only |
| Healthcare directory and provider directory | not personal data, kept |

## Holding data for an audit or dispute
`UPDATE users SET retention_hold = true WHERE email = '<email>';` (and `false` to release). The job skips accounts on hold.

## Safety net
`tests/test_retention.py::test_every_table_has_a_retention_decision` fails if a table exists that `HANDLED` in `retention_service.py` does not mention, or a table with a `dependent_id` that the job does not delete. Add the decision when you add a table.

## Settings
`RETENTION_DAYS` (60), `AUDIT_RETENTION_DAYS` (365), `RETENTION_BATCH` (50).
