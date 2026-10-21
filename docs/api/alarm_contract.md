# Remote Alarm Override contract (Task 3.7, FR-D3)

For Talha (Guardian "sound alarm" button, Dependent phone alarm) and Sarim (QA cases).

## The idea in 6 lines
1. Only the **Primary Guardian** can sound the alarm on the Dependent's phone (for example to find a confused person nearby). **A Secondary can never do it**, even if the Primary grants every permission. It cannot be delegated.
2. `POST /dependents/{id}/alarm` sends a **critical** push `remote_alarm` to the Dependent's phone. It lasts 60 s by default (10 to 300 s on request).
3. The **phone app** makes the sound and must override the silent / volume state, as far as Android allows (SRS FR-D3). The server only gives the order and writes it in the audit log.
4. If the push is late, the phone can ask: `GET /dependents/{id}/alarm` (the Dependent may call it for themself).
5. Only one alarm at a time. Starting again while one sounds changes nothing.
6. The Primary or the Dependent can stop it: `POST /dependents/{id}/alarm/stop`. The phone gets `remote_alarm_stop`.

## POST `/dependents/{id}/alarm`
Primary Guardian only. Body is optional: `{ "duration_s": 120 }` (10 to 300, else `422`). `201` for a new alarm, `200` with `already_active: true` if one is sounding.
```json
{ "alarm_id": "uuid", "status": "active", "triggered_by": "uuid", "triggered_at": "2026-10-18T03:00:00Z",
  "duration_s": 60, "expires_at": "2026-10-18T03:01:00Z", "stopped_at": null,
  "device_acknowledged_at": null, "already_active": false }
```
`status` is `active`, `stopped` or `expired`. `device_acknowledged_at` is set when the Dependent's phone acknowledges the notification (`POST /notifications/{id}/acknowledge`), so the Primary can see the order arrived.

Errors: `403 NOT_PRIMARY_GUARDIAN` (a Secondary), `403 NOT_LINKED_TO_DEPENDENT`, `403 FORBIDDEN` (a Dependent), `403 GUARDIAN_NOT_VERIFIED`, `401`.

## GET `/dependents/{id}/alarm`
The Primary, or the Dependent for themself. `{ "active": true, "alarm": { ... } }` or `{ "active": false, "alarm": null }`.

## POST `/dependents/{id}/alarm/stop`
The Primary, or the Dependent for themself. Reply: the alarm with `status: "stopped"`. `409 NO_ACTIVE_ALARM` if nothing is sounding.

## What the Dependent's phone receives
| type | priority | data |
|---|---|---|
| `remote_alarm` | critical | `alarm_id`, `duration_s`, `expires_at`, `triggered_by` |
| `remote_alarm_stop` | critical | `alarm_id` |
On `remote_alarm`: start the loud sound until `expires_at` or a `remote_alarm_stop` with the same `alarm_id`.

## Trying it by hand
As the Primary: `POST /dependents/{id}/alarm`. As the Dependent: `GET /notifications` shows the order. Try it as a Secondary: it is refused.
