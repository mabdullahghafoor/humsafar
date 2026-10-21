# Audit log contract (Task 6.6, FR-N3)

A permanent trail of sensitive actions, one list per Dependent. **Only the Primary Guardian can read it.** It cannot be edited or deleted through the API.

## Endpoint
| Call | Who | Result |
|---|---|---|
| `GET /dependents/{id}/audit-log` | Primary Guardian (verified) | `{items[], total, limit, offset}`, newest first |

Query parameters (all optional): `action` (exact name, e.g. `camera_view_started`), `actor_id` (a user id), `since` (ISO time, inclusive), `until` (ISO time, exclusive), `limit` (1-100, default 50), `offset` (0 or more). `total` is the size of the whole filtered list.

Each item:
```json
{
  "audit_id": "uuid",
  "action": "camera_view_started",
  "label": "Started watching the camera",
  "target_type": "camera_session",
  "target_id": "uuid or null",
  "occurred_at": "2026-10-22T09:30:00Z",
  "actor": {"user_id": "uuid", "full_name": "Sara Khan", "role": "guardian"}
}
```
Show `label` on screen; use `action` for icons or filters. An action the app does not know still has a readable `label`. `actor.role` is `guardian` or `dependent`.

## What is logged
Permission granted / revoked, record category hidden / shown, camera paired / unpaired / view started / view ended, emergency clip stored / viewed / deleted, medical records added / downloaded / changed / deleted / exported / shared / share opened, vitals added by hand / deleted / exported, appointments added / changed / cancelled / deleted, bookings, medication schedules, doses confirmed / extended and missed-dose escalation, wellness checks, emergency contact set / removed, wearable paired / unpaired, remote alarm, panic pressed / closed.
Not logged: band readings, location points, heartbeats, messages, and reading the log itself.

## Errors
`401 NOT_AUTHENTICATED`, `403 NOT_PRIMARY_GUARDIAN` (Secondary), `403 FORBIDDEN` (Dependent), `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`, `422 VALIDATION_ERROR` (bad `limit`, `offset`, id or time), `405` for any other method on this path.
