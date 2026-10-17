# Medication contract (Task 3.2, FR-F1)

For Talha (Guardian medicine screens, Dependent "take your medicine" screen) and Sarim (mockups). Same base URL and error envelope as the other contracts.

## The idea in 6 lines
1. A **Guardian** writes a schedule: drug, dosage, one or more times a day, daily or on chosen weekdays.
2. Times are **local clock times** in the server time zone (`timezone` in the reply, now `Asia/Karachi`). Send `"08:00"`, not a UTC time.
3. **15 minutes before** each dose the server prepares a **dose** and sends the Dependent a **standard reminder**. **At the dose time** it sends a **critical** "time to take it" alert (only if not yet confirmed).
4. The Dependent confirms in **two steps** (so a wrong tap is not a "taken"): step 1 asks, step 2 sends the proof token.
5. A dose has a `status`: `pending`, `taken` or `missed`. When `window_ends_at` passes (30 min after the time) an unconfirmed dose becomes **`missed`** and the Primary Guardian gets a critical alert (see "Missed dose" below).
6. Removing a schedule only **switches it off**; old doses stay for the adherence chart.

## Who may do what
| Action | Who |
|---|---|
| Create, change, switch off a schedule | Primary, or a verified Secondary with the `medication_management` permission |
| Read schedules and doses | The same Guardians, and the Dependent for their own |
| Confirm a dose (both steps) | The Dependent only |

Errors for the usual reasons: `401 NOT_AUTHENTICATED`, `403 FORBIDDEN` (wrong role), `403 MODULE_ACCESS_DENIED`, `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`.

## Schedules

### POST `/dependents/{id}/medications`  (201)
```json
{ "drug_name": "Metformin", "dosage": "500 mg", "times": ["08:00", "20:00"], "frequency": "daily" }
```
Weekly: `"frequency": "weekly", "days": ["mon", "thu"]`. Rules: 1 to 6 times (`HH:MM`, 24-hour, duplicates collapse); `days` required for weekly and not allowed for daily; names are trimmed. Max 30 active dose times per Dependent (`409 MEDICATION_LIMIT_REACHED`).
One row per time is created:
```json
{ "timezone": "Asia/Karachi",
  "items": [ { "schedule_id": "5a1c7e20-...", "dependent_id": "7b1c2e0a-...", "drug_name": "Metformin", "dosage": "500 mg",
               "time": "08:00", "frequency": "daily", "days": null, "active": true, "created_by": "2d5e8f10-...", "created_at": "2026-10-17T03:10:00Z" } ] }
```
A schedule never produces a dose for a time earlier than the moment it was created.

### GET `/dependents/{id}/medications?include_inactive=false`
Same `{timezone, items}` shape, ordered by time.

### PUT `/dependents/{id}/medications/{schedule_id}`
Any of: `drug_name`, `dosage`, `time` (`"HH:MM"`), `frequency`, `days`, `active`. Changing the time, days or `active` removes prepared doses that are not due yet. `404 MEDICATION_NOT_FOUND` for an unknown id.

### DELETE `/dependents/{id}/medications/{schedule_id}`  (204)
Switches it off. Repeating is fine.

## Doses

### GET `/dependents/{id}/medication-doses?from=&to=&status=`
Default range: 24 hours back to 24 hours ahead (ISO timestamps; at most 31 days). `status` = `pending|taken|missed`.
```json
{ "items": [ { "confirmation_id": "8c2d4e60-...", "schedule_id": "5a1c7e20-...", "drug_name": "Metformin", "dosage": "500 mg",
               "scheduled_for": "2026-10-17T03:00:00Z", "status": "pending", "confirmed_at": null, "window_ends_at": "2026-10-17T03:30:00Z",
               "open_alert_tier": null } ] }
```
A dose appears here from 15 minutes before its time (when the server prepares it, within about a minute). `open_alert_tier` is `null`, or `primary` / `secondary` while a missed-dose alert for this dose is open (use it to show "alert sent to Secondary").

## Two-step confirmation (Dependent only)

### Step 1: POST `/medications/{schedule_id}/confirm-request`
Body optional: `{ "confirmation_id": "..." }` to pick a dose. Default: the newest dose of that schedule that is not taken yet.
```json
{ "confirmation_id": "8c2d4e60-...", "drug_name": "Metformin", "dosage": "500 mg", "scheduled_for": "2026-10-17T03:00:00Z",
  "confirm_token": "eyJhbGciOi...", "expires_in_s": 120 }
```
Show: **"Did you take Metformin 500 mg?  [Yes, I took it]  [No]"**. Nothing is saved yet.
Errors: `404 NO_DOSE_DUE` (nothing waiting; the dose may not be prepared yet), `409 DOSE_ALREADY_CONFIRMED`, `404 MEDICATION_NOT_FOUND` (not your schedule).

### Step 2: POST `/medications/{schedule_id}/confirm`
```json
{ "confirm_token": "eyJhbGciOi..." }
```
```json
{ "confirmation_id": "8c2d4e60-...", "schedule_id": "5a1c7e20-...", "status": "taken", "confirmed_at": "2026-10-17T03:01:12Z", "already_confirmed": false }
```
* **Safe to repeat** (bad network): the second call returns `already_confirmed: true` and the **first** `confirmed_at`.
* The token lives 2 minutes and works for one dose and one person. Errors: `400 CONFIRM_TOKEN_EXPIRED` (start again from step 1), `400 CONFIRM_TOKEN_INVALID`.
* A dose that is already past its window can still be confirmed (the person took it late); it is recorded as `taken`, and it **closes the missed-dose alert** (see below).

## Notifications the Dependent receives (see `notification_contract.md`)
| `type` | `priority` | When | `data` |
|---|---|---|---|
| `medication_reminder` | `standard` | 15 min before the dose time | `schedule_id`, `confirmation_id`, `scheduled_for`, `drug_name`, `dosage` |
| `medication_due` | `critical` | At the dose time, until the window ends, if not confirmed | same |

Tapping either should open the step 1 screen for `data.schedule_id`.

## Missed dose (Task 3.3, FR-D1)

**What happens.** Every minute the server looks for doses that are still `pending` after `window_ends_at`. Each one becomes `missed` and opens **one** alert at the **Primary** level. The Primary gets a **critical** notification right away (`type: "missed_dose"`). Secondaries are **not** told yet (clarification 30). The Dependent is not sent a second alert (they already had the reminder and the "time to take it" alert).

The Primary's notification (see `notification_contract.md`):
```json
{ "type": "missed_dose", "priority": "critical", "title": "Missed medication",
  "body": "Test User has not taken Metformin (500 mg) due at 08:00.",
  "dependent_id": "7b1c2e0a-...", "event_id": "9e2f4a10-...",
  "data": { "tier": "primary", "schedule_id": "5a1c...", "confirmation_id": "8c2d...", "scheduled_for": "2026-10-17T03:00:00Z", "drug_name": "Metformin", "dosage": "500 mg" } }
```
Open the dose screen with `data.confirmation_id`, and show the two options below.

The alert is **not** raised when the schedule was switched off, or when the miss is found more than 6 hours late (for example the server was down). Those doses are still marked `missed` for the adherence chart.

### Option 1: give more time. POST `/dependents/{id}/medication-doses/{confirmation_id}/extend`
Guardian (Primary, or a Secondary with `medication_management`). Body optional: `{ "minutes": 30 }` (5 to 120, default 30). Returns the dose (same shape as the dose list).
* New deadline = `minutes` **after the current deadline**, or after **now** if the deadline has passed.
* A `missed` dose goes back to `pending` and its alert **closes**: everyone who was told gets a **standard** all-clear ("Test User was given more time for Metformin (500 mg)").
* The Dependent gets a **critical** alert (`type: "medication_extended"`): "Please take Metformin (500 mg) by 08:40, then confirm in the app." Same `data` as the reminder, so tapping it opens step 1.
* If the new deadline also passes without a confirmation, the dose is missed **again** and a **new** alert is raised.
* Errors: `404 DOSE_NOT_FOUND`, `409 DOSE_ALREADY_CONFIRMED`, `422 VALIDATION_ERROR` (minutes out of range), plus the usual 401/403.

### Option 2: escalate now. POST `/dependents/{id}/medication-doses/{confirmation_id}/escalate`
Same Guardians as above. No body.
```json
{ "confirmation_id": "8c2d4e60-...", "event_id": "9e2f4a10-...", "tier": "secondary", "notified": 1 }
```
* Moves the open alert from the Primary level to the **Secondary** level. Each Secondary who is verified **and** has the `emergency_alerts` permission gets the critical `missed_dose` alert (`data.tier: "secondary"`). `notified` says how many people that was. **0 means no Secondary is allowed to see alerts**: show that to the Guardian.
* The automatic timers and the external-contact step come with the escalation engine (Tasks 3.5 and 3.8); for now escalation is this manual button.
* Errors: `409 NO_OPEN_ALERT` (the dose has no open alert, for example it was never missed or was already closed), `409 ALREADY_ESCALATED`, `404 DOSE_NOT_FOUND`.

### Taking it late
If the Dependent confirms a `missed` dose (step 1 and 2 as before), the dose becomes `taken`, the alert closes, and everyone who was told gets a **standard** all-clear: "Test User took Metformin (500 mg) late."

### Trying a missed dose by hand (for the demo)
The automatic Postman folder cannot wait 30 minutes, so test the real miss like this: start the server with a 60-second window, create a schedule for 2 minutes from now, wait about 4 minutes, then read the Primary's `GET /notifications`.
```
$env:MEDICATION_WINDOW_S="60"
uvicorn app.main:app --reload
```
