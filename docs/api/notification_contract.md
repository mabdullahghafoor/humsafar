# Notification contract (Task 3.1, FR-M1 / FR-M2)

For Talha (Task 3.14: Guardian alert UI + Firebase) and for every later Phase 3 screen. Same base URL and error envelope as the other contracts.

## The idea in 5 lines
1. When something happens (geofence breach, low battery, phone offline, later: panic, missed dose, wellness check), the server saves a **notification** for each Guardian who must know, and tries to **push** it to their phone.
2. There are two tiers: **`critical`** (all alerts) and **`standard`** (all-clear messages such as "back in the safe zone"). Show them differently (colour, sound, channel).
3. The push can fail (phone offline, Firebase down). The notification is **always saved**, so the app must also show the inbox (`GET /notifications`). The inbox is the source of truth, the push is a nudge.
4. The person must **acknowledge** a critical alert (tap "I'm on it"). Unacknowledged critical alerts are the "no response" state that later escalates to the Secondary Guardian and then the external contact (Task 3.5).
5. Everyone sees only their own notifications.

## Who is told
| Situation | Told |
|---|---|
| Geofence breach, low battery, phone offline, possible fall | The **Primary** Guardian, plus each **Secondary** who is verified **and** has the `emergency_alerts` permission |
| Missed dose, missed wellness check (escalation chain) | First the Primary only. Then the permitted Secondaries: for a missed dose when a Guardian taps "escalate" (Task 3.3); automatically after a timeout in Task 3.5 |
| Panic Mode (Task 3.6) | **Every** linked Guardian, whatever their permissions (the one deliberate exception) |
| The Dependent | Never told about their own alert (they use the Dependent Mode screens) |

Only **active** links count. A Guardian whose link is revoked is not told.

## Endpoints (any signed-in user, own data only)

### GET `/notifications`
Query (all optional): `priority=critical|standard`, `unacknowledged=true`, `limit` (1 to 100, default 50), `before` (paging).
```json
{
  "items": [
    {
      "notification_id": "3c9a1d70-...", "type": "geofence_breach", "priority": "critical",
      "title": "Left the safe zone", "body": "Test User has left the safe zone.",
      "dependent_id": "7b1c2e0a-...", "event_id": "9e2f4a10-...",
      "data": { "tier": "primary", "dependent_id": "7b1c2e0a-...", "event_id": "9e2f4a10-..." },
      "sent_at": "2026-10-16T09:30:02Z", "acknowledged_at": null, "is_acknowledged": false
    }
  ],
  "unacknowledged_critical": 1,
  "next_before": null
}
```
* Newest first. For the next (older) page, pass the reply's `next_before` as `before`. `null` means no more.
* `unacknowledged_critical` counts **all** your waiting critical alerts, not just this page: use it for the badge.
* All-clear messages have `priority: "standard"` and `data.resolved: true`.
* `type` values so far: `geofence_breach`, `low_battery`, `device_offline`, `medication_reminder`, `medication_due` and `medication_extended` (sent to the **Dependent**), `missed_dose` (sent to Guardians, with `data.confirmation_id`; see `medication_contract.md`), `wellness_check_prompt` (critical, to the **Dependent**, with `data.response_id` and `data.deadline`) and `wellness_check` (critical, to the Primary, with `data.response_id`; see `wellness_contract.md`). The same alert is sent again to the next level when it climbs the chain (`data.tier` = `secondary`); see `escalation_contract.md`. `panic` (critical, to **every** linked Guardian, with `data.event_id`; see `panic_contract.md`; the all-clear is a standard `panic` notification titled "Panic alert closed"). `remote_alarm` and `remote_alarm_stop` (critical, to the **Dependent's phone** only, with `data.alarm_id`; see `alarm_contract.md`). `external_contact` (to the **Primary** only: standard "Emergency contact messaged", critical "No emergency contact set" or "Emergency contact could not be reached"; `data.result` = `sent` / `no_contact` / `failed`; see `emergency_contact_contract.md`). `message` (standard, to the receiver of a text message, with `data.message_id` and `data.from_user_id`; see `messaging_contract.md`). `voice_message` (critical, to the receiver of a priority voice message, with `data.message_id`, `data.from_user_id`, `data.duration_s`; see `messaging_contract.md`). `incoming_call` (critical, to the person being called, with `data.call_id`, `data.call_type`, `data.caller_id`, `data.expires_at`) and `missed_call` (standard, to the callee; see `call_contract.md`). `appointment_update` (standard, to the Dependent and the Guardians who may see appointments, except the person who made the change; `data.appointment_id`, `data.scheduled_at`, `data.provider_name`) and `appointment_reminder` (standard, the same people, 24 h and 1 h before; extra `data.lead_s`; see `appointment_contract.md`). `band_no_data` (standard, to the Primary and Secondaries with `health_records`: the paired wearable band sent nothing new for 30 minutes; all-clear when data returns; see `wearable_contract.md`). `booking_update` (standard, to the Dependent and the Guardians who may see health records, except the person who acted: a home-care request was made, confirmed, finished or cancelled; `data.request_id`, `data.provider_name`, `data.status`; see `booking_contract.md`). Coming: `fall`.
* `title` and `body` are English text from the server. For other languages, translate on the app side using `type` (and `data.resolved`).

### POST `/notifications/{notification_id}/acknowledge`
No body. Returns the notification with `is_acknowledged: true` and `acknowledged_at`.
* **Idempotent:** a second call changes nothing and keeps the first time.
* Someone else's notification, or an unknown id: `404 NOTIFICATION_NOT_FOUND` (deliberately the same, so ids cannot be probed).
* Call it when the person actually opens or confirms the alert, not when the list loads.

### PUT `/devices/push-token`
```json
{ "token": "<Firebase registration token>", "platform": "android" }
```
Returns `{ "registered": true }`. Call it **after every login** and whenever Firebase gives the app a new token. Calling it again is harmless. If the same phone token is registered by another account, it **moves** to that account (a shared phone).

### DELETE `/devices/push-token?token=<token>`
Returns `{ "registered": false }`. Call it **on logout**, so the next person on that phone does not get your alerts. Removing a token that is not yours does nothing.

Errors for all four: `401 NOT_AUTHENTICATED` / `TOKEN_*`, `422 VALIDATION_ERROR` (token shorter than 20 characters, `platform` other than `android`, bad `priority`, `limit` out of range).

## What the push looks like (for Task 3.14)
The server sends a Firebase message with a `notification` (title, body) and this `data`:
```json
{ "notification_id": "...", "type": "geofence_breach", "priority": "critical", "event_id": "..." }
```
* `priority: "critical"` should open a **high-importance Android channel** (sound, heads-up). `standard` uses a normal channel.
* When the app opens from a push, call `GET /notifications` (the push may have been missed) and show the alert, then `acknowledge` when the person confirms it.
* **Until Firebase is connected the server uses a mock sender** (it only records the message). The tokens, inbox and acknowledgment work for real now. Talha: please create the Firebase project and send Abdullah the service-account key when you start 3.14 (see `../backend/sds_clarifications.md` item 29).

## Timing
* Alerts that come from a phone upload (geofence breach, low battery, all-clear) are created **inside that upload request**, so Guardians are told in seconds.
* Alerts that come from silence (phone offline) and all later timers are created by the background job, at most **about a minute** after the event.

## For the backend team (Tasks 3.2 to 3.8)
* `notification_service.notify_dependent_guardians(db, dependent_id, type, title, body, audience=..., tier=..., dedupe_key=...)` is the one call every Phase 3 feature uses. Audiences: `linked_permitted`, `by_tier`, `all_linked` (panic). The `dedupe_key` makes it safe to call twice.
* Or open an `escalation_events` row with a known `trigger_type` (`panic`, `missed_dose`, `wellness_check`, `fall`, ...). The dispatcher (`notification_service.dispatch_events`, run after every location fix and every minute) tells the right people exactly once.
* `notification_service.unacknowledged_critical(db, older_than_s, event_id)` returns the "no response" list for the escalation engine.
* A unique index on `(user_id, payload->>'dedupe_key')` guarantees one notification per person per event even when two processes dispatch at once.
