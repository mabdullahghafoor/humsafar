# Location API contract (Task 2.1, FR-C1 / FR-C4)

For Talha (Tasks 2.6 Live Map and 2.7 background location service). Base URL in development: `http://localhost:8000`
(Android emulator: `http://10.0.2.2:8000`). Errors use the usual envelope `{ "error": { "code", "message", "details" } }`.

## How it works in one minute
The Dependent's phone sends a GPS fix. The server stores it, works out whether the Dependent is **moving**,
**stationary** or **idle**, and replies with `next_update_interval_s`: *how many seconds the phone must wait before sending the next fix*.
The phone does not decide the polling rate on its own; it just obeys the number in the last reply. That is the adaptive
frequency of FR-C1 and the main battery saver (NFR-02).

| State | Meaning | Default wait |
|---|---|---|
| `moving` | speed >= 0.8 m/s, or moved >= 25 m (and more than the GPS error) since the last fix. The very first fix also counts as moving. | 10 s |
| `stationary` | not moving | 60 s |
| `idle` | not moving for 10 minutes or more | 180 s |

The numbers are settings on the server (`LOCATION_*` in `app/core/config.py`), so they can be tuned without changing the app.
Until the first reply arrives, or if the phone is offline, use 60 s.

## POST `/dependents/{dependent_id}/location`  (the phone sends a fix)
**Auth:** the Dependent's own access token. `dependent_id` must be the logged-in Dependent. A Guardian or another Dependent gets `403 FORBIDDEN`.

Request:
```json
{ "lat": 24.8607, "lng": 67.0011, "recorded_at": "2026-10-16T09:30:00Z", "battery_level": 82, "speed_mps": 0.4, "accuracy_m": 12 }
```
| Field | Required | Notes |
|---|---|---|
| `lat`, `lng` | yes | -90..90 and -180..180 |
| `recorded_at` | no | ISO time **with timezone**. Default: server time. Use it when sending a fix that was saved while offline (up to 24 h old). More than 5 minutes ahead of the server is rejected |
| `battery_level` | no | 0..100 (feeds the low-battery alert, Task 2.3) |
| `speed_mps` | no | speed from the phone GPS |
| `accuracy_m` | no | GPS error radius. A shift smaller than this is not treated as movement |

Response `200`:
```json
{ "log_id": "0f8c6a52-...", "recorded_at": "2026-10-16T09:30:00Z", "movement_state": "stationary", "next_update_interval_s": 60, "duplicate": false, "geofence_status": "inside", "breach_started": false, "low_battery": false, "low_battery_started": false }
```
* `duplicate: true` means this exact fix (same time and place) was already stored. Retrying after a lost reply is safe.
* When sending buffered offline fixes, send them oldest first and use the interval from the last reply.

Errors: `403 FORBIDDEN`, `401 NOT_AUTHENTICATED / TOKEN_EXPIRED`, `422 VALIDATION_ERROR`, `422 TIMESTAMP_IN_FUTURE`, `422 TIMESTAMP_TOO_OLD`.

## GET `/dependents/{dependent_id}/location`  (latest position, Guardian side)
**Auth:** Guardian. The Primary always passes. A Secondary needs a verified account **and** the `live_location` permission, checked on every call (a revoke works on the next request).
```json
{ "dependent_id": "7b1c2e0a-...", "location": { "lat": 24.865, "lng": 67.0011, "recorded_at": "2026-10-16T09:30:00Z", "battery_level": 82 }, "age_seconds": 4, "is_stale": false }
```
* `location` is `null` (and `is_stale` true) until the Dependent has sent a first fix.
* `is_stale` is true when the newest fix is older than 8 minutes. Show "last seen N minutes ago" instead of a live dot.

Errors: `403 MODULE_ACCESS_DENIED`, `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`, `403 FORBIDDEN` (a Dependent token), `401`.

## GET `/dependents/{dependent_id}/location/history`  (FR-C4)
Same permission as above. Query: `from`, `to` (ISO times with timezone, both optional), `limit` (1..500, default 100). Newest first.
```json
{ "dependent_id": "7b1c2e0a-...", "count": 2, "points": [ { "lat": 24.865, "lng": 67.0011, "recorded_at": "...", "battery_level": null }, { "...": "..." } ] }
```
Errors: `422 INVALID_RANGE` when `from` is later than `to`, plus the permission errors above.

## Notes
* While `low_battery` is true the wait is cut to at most 60 s (see `device_health_contract.md`).
* Only the position and battery are stored. The movement state is calculated on each request and not saved (the locked schema has no column for it).
* Geofence breach checks run on this POST (Task 2.2), so alerts need no extra call from the phone. `geofence_status` and `breach_started` in the reply come from that check; see `geofence_contract.md`.
