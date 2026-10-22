# Analytics contract (Task 7.1, FR-Q1)

Medication adherence and vitals trends for the **Guardian** dashboard. Read only; nothing new is stored, it is all computed from the medicine doses (3.2/3.3) and the vital readings (5.3 typed in, 5.4 band). Never cached (`Cache-Control: private, no-store`).

## Endpoints
| Call | Who | Needs |
|---|---|---|
| `GET /dependents/{id}/analytics/adherence?days=30` | Guardian | `medication_management` (Primary always) |
| `GET /dependents/{id}/analytics/vitals?days=30&metric_type=` | Guardian | `health_records` (Primary always) |
| `GET /dependents/{id}/analytics?days=30` | Guardian | either; a part without permission is `null`, neither is 403 |

`days`: 1 to 90, default 30, **today counts as day 1** (`days=7` = today and the 6 days before). Days are local days in `Asia/Karachi` (`timezone` is in every answer). Outside 1..90 gives `422 VALIDATION_ERROR`. The Dependent gets `403 FORBIDDEN`; a Guardian not linked gets `403 NOT_LINKED_TO_DEPENDENT`; a Secondary without the permission gets `403 MODULE_ACCESS_DENIED`.

## Adherence
```json
{
  "days": 7, "from_date": "2026-10-16", "to_date": "2026-10-22", "timezone": "Asia/Karachi",
  "taken": 5, "missed": 1, "waiting": 0, "rate_percent": 83.3,
  "previous": {"taken": 3, "missed": 3, "rate_percent": 50.0},
  "change_points": 33.3, "change": "improving",
  "perfect_days_in_a_row": 2,
  "daily": [{"date": "2026-10-22", "taken": 1, "missed": 0, "rate_percent": 100.0}],
  "by_medicine": [{"drug_name": "Metformin", "dosage": "500 mg", "taken": 5, "missed": 1, "rate_percent": 83.3}]
}
```
- Only decided doses count. `rate_percent = taken / (taken + missed) x 100`; **null** when nothing is decided yet (show "no data", not 0 %).
- `waiting`: due but not yet confirmed or missed. Not in the rate.
- `previous`: the same number of days just before. `change` is `improving` / `declining` (5 points or more), `steady`, or `not_enough_data` (one of the rates is null).
- `perfect_days_in_a_row`: counting back from today; days with no doses are skipped; a day with a missed dose ends the count.
- `daily`: **every** day of the period, oldest first, so a chart needs no gap filling. `by_medicine`: one row per medicine + dosage (a removed medicine keeps its history).

## Vitals
```json
{
  "days": 7, "from_date": "2026-10-16", "to_date": "2026-10-22", "timezone": "Asia/Karachi",
  "metrics": [{
    "metric_type": "blood_pressure", "unit": "mmHg", "count": 3, "manual_count": 3, "wearable_count": 0,
    "avg": 130.0, "min": 120.0, "max": 140.0, "avg_diastolic": 90.0, "min_diastolic": 80.0, "max_diastolic": 100.0,
    "latest": {"value": 140.0, "diastolic": 100.0, "recorded_at": "2026-10-22T08:00:00Z", "source": "manual"},
    "trend": "rising", "change_percent": 8.3,
    "daily": [{"date": "2026-10-20", "count": 1, "avg": 120.0, "min": 120.0, "max": 120.0, "avg_diastolic": 80.0, "min_diastolic": 80.0, "max_diastolic": 80.0}]
  }]
}
```
- All five metrics are always listed, in this order: `blood_pressure`, `blood_sugar`, `spo2`, `temperature`, `heart_rate`. `count: 0` means no readings (then `avg`, `latest` are null and `daily` is empty). With `metric_type=` only that one is returned.
- For blood pressure `value`/`avg`/`min`/`max` are the top number and the `*_diastolic` fields the bottom number. Other metrics have no `*_diastolic`.
- Units: mmHg, mg/dL, %, C, bpm. Manual and band readings are counted together; `manual_count` / `wearable_count` say how many came from where.
- `daily`: **only days that have readings**, oldest first (average, min, max, count of that day).
- `trend`: average of the second half of the period against the first half: `rising`, `falling`, `steady` (change under 3 %), or `not_enough_data` (no reading in one of the halves). `change_percent` is that change. **It describes numbers only; never show it as good or bad, never as advice.**

## Overview
`GET /dependents/{id}/analytics` returns `{dependent_id, days, adherence, vitals}`. Use it for the dashboard screen; `null` for a part means "this Guardian has no permission for it", so hide that section.

## For the screens (Talha / Sarim)
Adherence: a bar per day from `daily` plus the big number `rate_percent`, an arrow from `change`. Vitals: a line per metric from `daily` (blood pressure: two lines). Wording suggestion for `trend`: "Going up", "Going down", "Steady", "Not enough readings yet".
