# Appointments contract (Task 5.1, FR-G4)

For Talha (appointments screen, task 5.6) and Sarim (QA cases, 5.10). Doctor appointments for a Dependent, with reminders to the Dependent and to the Guardians.

## The idea in 7 lines
1. An appointment has a **doctor / clinic** (`provider_name`), a **time** (`scheduled_at`, with a time zone, in the future) and an optional **note**.
2. **Who:** the Dependent (own appointments), the **Primary** Guardian always, a **Secondary** with the `health_records` permission (the same permission as the Medical Vault). Everyone with access can add, change, cancel and delete.
3. Past times are refused (`422 APPOINTMENT_IN_PAST`). The same doctor at the same time twice is refused (`409 APPOINTMENT_EXISTS`). At most **100** appointments still to come (`409 APPOINTMENTS_LIMIT`).
4. **Cancelling** keeps the appointment in the history (`status: "cancelled"`). **Deleting** removes it completely. A cancelled appointment cannot be changed (`409 APPOINTMENT_CANCELLED`).
5. When an appointment is **added, moved or cancelled**, everyone else involved gets a standard `appointment_update` notification (`data.appointment_id`, `data.scheduled_at`, `data.provider_name`). The person who did it does not.
6. **Reminders** (standard `appointment_reminder`, same data plus `data.lead_s`) go to the Dependent and to each Guardian who may see appointments: **24 hours** and **1 hour** before. No "24 hours to go" is sent for an appointment made at short notice, only the closest reminder is sent after a server restart, and a **moved** appointment gets its reminders again for the new time. A Secondary who loses `health_records` stops receiving them.
7. Reminders are sent by a background job that runs every minute, so a reminder can be up to about a minute late.

## The appointment object
`{ appointment_id, dependent_id, provider_name, scheduled_at, notes, status: "scheduled"|"cancelled", created_by, created_by_name, created_at, is_upcoming }`

## Endpoints (`{id}` = the Dependent's user id)
| Method and path | What |
|---|---|
| POST `/dependents/{id}/appointments` | Body `{ "provider_name": "Dr. Ayesha Khan", "scheduled_at": "2026-11-03T10:30:00+05:00", "notes": "optional" }`. `201` |
| GET `/dependents/{id}/appointments` | Query `when` = `upcoming` (default, soonest first) / `past` (cancelled or already happened, latest first) / `all`; `limit` (1 to 100, default 30), `offset`. Reply `{ items, total, limit, offset }` |
| GET `/dependents/{id}/appointments/{appointment_id}` | One appointment |
| PATCH `/dependents/{id}/appointments/{appointment_id}` | Change `provider_name`, `scheduled_at`, `notes` (send only what changes; `notes: ""` clears it) |
| POST `/dependents/{id}/appointments/{appointment_id}/cancel` | Cancel (safe to repeat) |
| DELETE `/dependents/{id}/appointments/{appointment_id}` | Remove completely. `204` |

## Errors
`NOT_AUTHENTICATED` 401. `FORBIDDEN`, `NOT_LINKED_TO_DEPENDENT`, `MODULE_ACCESS_DENIED`, `GUARDIAN_NOT_VERIFIED` 403 (same meaning as in the Medical Vault). `APPOINTMENT_NOT_FOUND` 404. `APPOINTMENT_EXISTS`, `APPOINTMENTS_LIMIT`, `APPOINTMENT_CANCELLED` 409. `APPOINTMENT_IN_PAST`, `VALIDATION_ERROR` 422 (a `scheduled_at` without a time zone is a `VALIDATION_ERROR`).

## What the screens do
- Show `scheduled_at` in the phone's local time. Send it back with a time zone (for example `DateTime.toIso8601String()` on a UTC or local `DateTime`).
- Upcoming tab = `when=upcoming`; History tab = `when=past`.
- Open the app from a reminder with `data.appointment_id`.
