# Device health contract (Task 2.3, FR-L1 / FR-L2)

For Talha (Tasks 2.6 and 2.7) and for Guardian dashboard screens. Same base URL and error envelope as the other contracts.

## How it works
There is **no new endpoint for the Dependent's phone**. The phone already sends a location fix every 10 to 180 seconds
(`POST /dependents/{id}/location`, see `location_contract.md`). Each fix may carry `battery_level` (0 to 100), and the fix itself is the
"I am alive" signal. So:

| Alert | When it opens | When it closes | Recorded as |
|---|---|---|---|
| **Low battery** (FR-L1) | a fix shows battery **15% or lower** | a fix shows battery **above 20%** (so 15, 16, 15 does not flap) | `escalation_events` row, type `low_battery` |
| **Offline** (FR-L2) | no fix for **10 minutes**; a background job checks every minute | any new fix | `escalation_events` row, type `device_offline` |

* One alert per episode: more low readings or more minutes offline do not create more alerts.
* The two alerts are separate on purpose (a dead battery and a lost signal need different reactions).
* Only the newest fix decides: a late buffered upload cannot open or close an alert.
* Sending the push notification to Guardians arrives with the notification service (Task 3.1). Until then, show the state from `device-health`.

## What the phone must do (Talha, Task 2.7)
1. Put `battery_level` in every location fix.
2. When Android says the battery is low or the phone is shutting down (`ACTION_BATTERY_LOW`, `ACTION_SHUTDOWN`), **send one fix immediately**. That is the "last-known location before shutdown" (FR-L1.3): the server keeps every fix, and the newest one is the last-known location.
3. While the battery is low (`low_battery: true` in the reply), the server shortens `next_update_interval_s` to at most 60 s, so the final position is as fresh as possible. Just obey the number.

The location reply now has two more fields: `low_battery` (an alert is open) and `low_battery_started` (this fix opened it).

## GET `/dependents/{dependent_id}/device-health`
**Auth:** Guardian. Primary always; a Secondary needs a verified account and the `live_location` permission (checked on every call).
```json
{
  "dependent_id": "7b1c2e0a-...",
  "battery_level": 14, "battery_reported_at": "2026-10-16T09:30:00Z",
  "low_battery": true, "low_battery_since": "2026-10-16T09:29:00Z",
  "connectivity": "online", "last_seen_at": "2026-10-16T09:30:00Z", "seconds_since_seen": 12,
  "offline_alert_open": false, "offline_alert_since": null,
  "probable_cause": null,
  "last_known_location": { "lat": 24.8607, "lng": 67.0011, "recorded_at": "2026-10-16T09:30:00Z", "battery_level": 14 },
  "thresholds": { "low_battery_pct": 15, "battery_recover_pct": 20, "offline_after_s": 600 }
}
```
* `battery_level` is from the newest fix that had a battery reading (a fix without one does not erase it).
* `connectivity`: `online`, `offline` (newest fix older than 10 minutes), or `unknown` (the phone has never reported).
* `probable_cause` (only when offline): `battery_depleted` if the last battery reading was 5% or lower, otherwise `connectivity_or_unknown`. Show "phone probably ran out of battery" or "phone has lost its connection".
* `offline_alert_since` is when the system noticed (up to a minute after the threshold), not when the phone went quiet. Use `last_seen_at` for "last seen".
* `last_known_location` is `null` until the first fix.

Errors: `403 MODULE_ACCESS_DENIED`, `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`, `403 FORBIDDEN` (a Dependent token), `401`.

## For the backend team: the background job runner
`app/core/scheduler.py` runs registered jobs every `SCHEDULER_TICK_S` (60 s) inside the app. Phase 3 timers (missed doses, wellness-check grace, escalation timeouts) will register there. Set `SCHEDULER_ENABLED=false` to turn it off (the tests do). A job that fails is logged and retried next tick. Several app processes may run it at once; jobs lock the Dependent row, so only one alert is ever opened.
