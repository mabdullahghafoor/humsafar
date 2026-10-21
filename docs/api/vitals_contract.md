# Manual vitals contract (Task 5.3, FR-H1)

For Talha (vitals screens, task 5.7) and Sarim (QA cases, 5.10). The Dependent, or a Guardian, types a reading of blood pressure, blood sugar, oxygen saturation (SpO2) or body temperature. The server stores it, lists it, shows the latest values, and can put it into a PDF.

## The idea in 8 lines
1. **Four manual metrics:** `blood_pressure`, `blood_sugar`, `spo2`, `temperature`. A fifth, `heart_rate`, comes only from the wearable band (Task 5.4, `wearable_contract.md`) and **cannot be typed by hand** (`422`). It shows in `latest` as `null` until the band sends data. Band readings have `source: "wearable"` and `recorded_by: null`; the Primary can delete them. Filter with `metric_type` so a band's many readings do not bury typed ones.
2. **Who:** the Dependent (own data), the Primary Guardian, and a Secondary with the `health_records` permission (the same gate as the Medical Vault). Everyone else gets `403`.
3. **Fixed units in every reply:** mmHg, mg/dL, %, degrees Celsius. A person may type blood sugar in mmol/L or temperature in Fahrenheit; the server converts and returns the fixed unit. Never convert again in the app.
4. **Blood pressure = two numbers:** `value` (top, systolic) and `diastolic` (bottom). The other metrics send only `value`.
5. **Possible-number checks only.** The server never says "high", "low" or "normal" and the reply has no such field (no medical advice).
6. **Delete:** whoever typed the reading, or the Primary Guardian (`can_delete` tells the screen). Readings cannot be edited: delete and add again.
7. **Safe retry:** send a new random `client_id` (UUID) with each reading. A repeat gives `200` + `already_saved: true` and saves nothing twice. The same `client_id` with other numbers gives `409 CLIENT_ID_REUSED`.
8. At most **10,000** typed readings per Dependent (`409 VITALS_LIMIT`). Add, delete and export are written to the audit log.

## Allowed values
| metric_type | value | other fields | Stored unit |
|---|---|---|---|
| `blood_pressure` | top number 50 to 300 | `diastolic` 30 to 200, required, lower than `value`; `unit` only `mmHg` | mmHg |
| `blood_sugar` | 10 to 1000 mg/dL | `unit` `mg/dL` (default) or `mmol/L` (x 18.016); optional `context`: `fasting`, `after_meal`, `random` | mg/dL |
| `spo2` | 50 to 100 | `unit` only `%` | % |
| `temperature` | 30 to 45 C (86 to 113 F) | `unit` `C` (default) or `F` | C |

Values are rounded to one decimal. `diastolic` is only for blood pressure and `context` only for blood sugar (`422 VALIDATION_ERROR` otherwise). A number outside the range is `422 VITAL_OUT_OF_RANGE` with `details.field` naming the wrong field.

## The reading object
`{ reading_id, dependent_id, metric_type, value, diastolic, unit, context, note, source, recorded_at, created_at, recorded_by, recorded_by_name, can_delete, already_saved }`
`source` is `manual` (the band will use `band`). `recorded_at` is when it was measured; `created_at` when it was saved. `already_saved` only matters on `POST`.

## Endpoints (`{id}` = the Dependent's user id)
| Method and path | What |
|---|---|
| POST `/dependents/{id}/vitals` | Save a reading. Body: `metric_type`, `value`, optional `diastolic`, `unit`, `context`, `recorded_at` (ISO time **with a time zone**, default now, not in the future, at most 365 days back), `note` (up to 200), `client_id`. `201`; `200` for a repeat |
| GET `/dependents/{id}/vitals` | List, newest measurement first. Query: `metric_type`, `from`, `to` (with a time zone), `limit` (1 to 200, default 50), `offset`. Reply `{ items, total, limit, offset }` |
| GET `/dependents/{id}/vitals/latest` | `{ dependent_id, latest: { blood_pressure, blood_sugar, spo2, temperature, heart_rate } }`, each the newest reading or `null` |
| GET `/dependents/{id}/vitals/{reading_id}` | One reading (`404 VITAL_NOT_FOUND`) |
| DELETE `/dependents/{id}/vitals/{reading_id}` | `204`. Others: `403 VITAL_MODIFY_DENIED` |
| GET `/dependents/{id}/vitals/export` | A separate **vitals PDF**: query `scope` (`complete` / `year` / `month`), `year`, `month` |

## Putting vitals in the other PDFs (FR-H1 "separate or combined")
- `GET /dependents/{id}/records/export?include_vitals=true` adds a **Vitals** section to the Medical Vault PDF (default `false`).
- `POST /dependents/{id}/records/share` accepts `include_vitals: true` (default `false`); the link and the share list show `include_vitals`. The doctor's PDF then contains the vitals. (A Secondary needs `health_records`, the same as for the vault.)
- Band readings are not listed one by one in a PDF: they appear as one line per day and metric (average, lowest, highest, count).
- A PDF holds the newest 1,000 typed readings of the period (a note says so if more matched). Months and years are counted in Pakistan time.

## Errors
`401 NOT_AUTHENTICATED`, `403 MODULE_ACCESS_DENIED` / `FORBIDDEN`, `404 VITAL_NOT_FOUND`, `409 CLIENT_ID_REUSED`, `409 VITALS_LIMIT`, `422 VALIDATION_ERROR`, `422 VITAL_OUT_OF_RANGE`, `422 INVALID_DATE`.
