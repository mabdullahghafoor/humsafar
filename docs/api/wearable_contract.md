# Wearable band contract (Task 5.4, FR-H2) - mock data first

For Talha (band pairing and "My band" screens, task 5.8) and Sarim (QA cases, 5.10). The band reaches the server through the **Dependent's phone**: band --Bluetooth--> phone --HTTPS--> server. The real Bluetooth link and device are Task 5.5 (needs the spike 2.4 and the final band); everything here already works with fake data, so the screens can be built now.

## The idea in 9 lines
1. **One band per Dependent.** Pair it once (the phone knows the band's Bluetooth address from its scan). Pairing the same band twice is fine; a different band needs an unpair first (`409 BAND_ALREADY_PAIRED`).
2. **Who pairs / unpairs:** the Dependent or the Primary Guardian. **Who sends data:** only the Dependent's own phone (`POST .../wearable/sync`).
3. **Who reads the status:** the same people who may see health data (the Dependent, the Primary, a Secondary with `health_records`).
4. **What the band sends:** `heart_rate` (bpm), and `spo2` / `temperature` if the band has those sensors. **No battery** (clarification 88: the band shows its charge with 3 LEDs) and **no steps yet** (waits for the sensor list, clarification 89).
5. The readings are stored as ordinary vitals with `source: "wearable"`, so `GET /vitals`, `GET /vitals/latest` and the PDFs (Task 5.3) already show them. Heart rate is now filled in `latest`.
6. **Safe retry:** a sample is identified by metric + measured time. The same batch sent twice stores once (`duplicates` in the reply). No `client_id` needed.
7. **Bad readings do not block anything:** an impossible, future or too-old reading is skipped and listed in `rejected`; the others are kept.
8. **"No data" detection (clarification 88):** if a paired band produces **no new measurement for 30 minutes**, the Primary (and Secondaries with `health_records`) get a **standard** notification `band_no_data`; it closes by itself, with an all-clear, when a new measurement arrives. Old readings the band stored and uploads late do **not** count as new. No alert while the phone itself is offline (that has its own `device_offline` alert). Nothing else in the app is blocked by a silent band.
9. **Demo data:** `POST .../wearable/mock` makes fake heart-rate readings so the screens and the demo work without the band (can be switched off on the server).

## Endpoints (`{id}` = the Dependent's user id)
| Method and path | Who | What |
|---|---|---|
| POST `/dependents/{id}/wearable` | the Dependent, or the Primary | Pair. Body `{ ble_address, name? }`. Address like `C4:5B:BE:12:34:56` (dashes and small letters are cleaned). `201` with the band, `200` if the same band is already paired |
| GET `/dependents/{id}/wearable` | health-data readers | Status (below) |
| DELETE `/dependents/{id}/wearable` | the Dependent, or the Primary | Unpair. `204`, safe to repeat. Readings already stored stay; an open "no data" notice is closed |
| POST `/dependents/{id}/wearable/sync` | the Dependent's own phone | Body `{ readings: [ { metric_type, value, recorded_at } ] }`, 1 to 500. `409 NO_BAND` if not paired |
| POST `/dependents/{id}/wearable/mock` | the Dependent, or the Primary | Demo data. Body (optional) `{ count 1-200 (30), interval_s 10-3600 (60) }`. `404` when switched off |

### Reading values
| metric_type | value | Skipped when |
|---|---|---|
| `heart_rate` | bpm | not 20 to 250 |
| `spo2` | percent | not 50 to 100 |
| `temperature` | degrees Celsius | not 30 to 45 |

`recorded_at` needs a time zone, must not be in the future (5 minutes of slack) and not older than 7 days.

### Sync reply
`{ received, stored, duplicates, rejected: [ { index, reason } ], last_sync_at }` - `index` is the position in the list you sent (from 0). Always `200` when the request is well formed, even if some readings were skipped.

### Status reply
`{ dependent_id, status, device, last_data_at, seconds_since_data, no_data_alert_open, no_data_alert_since, no_data_after_s, latest_heart_rate }`
- `status`: `not_paired`, `waiting_for_first_data` (paired, nothing yet), `receiving`, `no_data` (nothing new for `no_data_after_s` = 1800 s, counted from pairing if it never sent anything). The status is worked out from the clock when you ask, so it is right even before the server job has run; `no_data_alert_open` says whether the notification was raised.
- `device`: `{ device_id, dependent_id, ble_address, name, paired_at, last_sync_at }` (`last_sync_at` = the time of the newest measurement received).
- `latest_heart_rate`: the newest heart-rate reading (a normal vitals object) or `null`.

## Notification
`band_no_data` - **standard** priority, to the Primary and to Secondaries with `health_records`; `data.dependent_id`, `data.event_id`, `data.tier`. The all-clear is a standard `band_no_data` notification with `data.resolved: true`. The event also shows in the alerts list (`GET /dependents/{id}/escalations`) but it never climbs the escalation chain.

## PDFs
Typed readings are listed one by one. The band's readings are **summarised per day and metric** (average, lowest, highest, number of readings), because a band sends hundreds a day.

## Errors
`401 NOT_AUTHENTICATED`, `403 FORBIDDEN` / `NOT_PRIMARY_GUARDIAN` / `MODULE_ACCESS_DENIED`, `404 NOT_FOUND` (demo data switched off), `409 BAND_ALREADY_PAIRED`, `409 NO_BAND`, `422 VALIDATION_ERROR`.
