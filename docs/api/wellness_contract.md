# Wellness check contract (Task 3.4, FR-D4)

For Talha (Guardian schedule screen, Dependent "Are you OK?" screen) and Sarim (mockups). Same base URL and error envelope as the other contracts.

## The idea in 6 lines
1. A **Guardian** sets up to **3 check times a day** (local clock time, `timezone` in the reply, now `Asia/Karachi`), each with a **grace period** (5 to 180 min, default 30).
2. **At the check time** the Dependent gets a **critical** alert "Are you OK?". `data.response_id` is the id used to answer.
3. The Dependent taps **"I am OK"** (`POST /wellness-checks/{response_id}/respond`). Repeating it is safe.
4. If there is no answer when the grace period ends, the server looks for **device activity** (a location fix in the last 30 min). If there is one, the check closes as `device_active`. No alert.
5. If there is no answer and no activity, the check becomes `escalated` and the **Primary Guardian** gets a critical alert.
6. If the Dependent answers later, the alert closes and everyone who was told gets a standard all-clear.

## Who may do what
| Action | Who |
|---|---|
| Add, change, switch off a check | Primary, or a verified Secondary with `emergency_alerts` |
| Read checks and history | The same Guardians, and the Dependent for their own |
| Answer "I am OK" | The Dependent only |

Usual errors: `401 NOT_AUTHENTICATED`, `403 FORBIDDEN`, `403 MODULE_ACCESS_DENIED`, `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`.

## Schedule

### POST `/dependents/{id}/wellness-checks`  (201)
```json
{ "times": ["08:00", "20:00"], "grace_period_min": 30 }
```
1 to 3 times (`HH:MM`, 24-hour, duplicates in the request collapse). Max 3 active checks (`409 WELLNESS_LIMIT_REACHED`). A time that already exists: `409 WELLNESS_TIME_EXISTS` with `error.details.times`; nothing is saved. Reply:
```json
{ "timezone": "Asia/Karachi", "default_times": ["08:00", "14:00", "20:00"], "default_grace_period_min": 30,
  "items": [ { "wc_id": "uuid", "time": "08:00", "grace_period_min": 30, "active": true } ] }
```

### POST `/dependents/{id}/wellness-checks/default-schedule`  (201)
Adds 08:00, 14:00 and 20:00 with 30 min grace. `409 SCHEDULE_ALREADY_EXISTS` if the Dependent already has any active check.

### GET `/dependents/{id}/wellness-checks`
Same reply as above. `?include_inactive=true` also shows switched-off checks.

### PUT `/dependents/{id}/wellness-checks/{wc_id}`
Send any of `time`, `grace_period_min`, `active`. `404 WELLNESS_CHECK_NOT_FOUND` for an unknown id.

### DELETE `/dependents/{id}/wellness-checks/{wc_id}`  (204)
Switches it off (the row is kept). Safe to repeat.

## Prompts and answers

### GET `/dependents/{id}/wellness-check-responses`
Query: `from`, `to` (default last 7 days), `status` (`pending`, `responded`, `device_active`, `escalated`, `cancelled`).
```json
{ "items": [ { "response_id": "uuid", "wc_id": "uuid", "prompted_at": "2026-10-18T03:00:00Z", "deadline": "2026-10-18T03:30:00Z",
  "status": "pending", "responded_at": null, "open_alert_tier": null } ] }
```
`open_alert_tier` is `primary` while an unanswered-check alert is open, otherwise `null`.

### POST `/wellness-checks/{response_id}/respond`
Dependent only. Reply:
```json
{ "response_id": "uuid", "status": "responded", "responded_at": "2026-10-18T03:04:00Z", "already_responded": false }
```
Answering again returns the first time with `already_responded: true`. Another person's id gives `404 WELLNESS_CHECK_NOT_FOUND`.

## Notifications
| type | priority | to | data |
|---|---|---|---|
| `wellness_check_prompt` | critical | the Dependent | `response_id`, `deadline` |
| `wellness_check` | critical | the Primary | `response_id`, `tier` |
Body of the alert: "{name} has not answered the {time} wellness check, and their phone shows no recent activity." After a late answer the Primary gets a standard "Wellness check answered".

## Trying it by hand
Add a check for 2 minutes from now (Karachi time) with grace 5. Wait for the prompt in `/notifications`. Do not answer. After the grace period plus about a minute, the Primary's inbox shows the alert. Then answer: the alert closes.
