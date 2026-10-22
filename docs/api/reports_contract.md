# Summary reports contract (Task 7.2, FR-Q2)

A weekly or monthly PDF summary of the adherence and vitals trends (the numbers of `analytics_contract.md`) for the **Guardian**. Reports are made automatically by a background job or on demand, kept in the app, and downloaded as PDF. Guardians only.

Who sees what: the **Adherence** part needs `medication_management`, the **Vitals** part needs `health_records` (the Primary has both). A report contains only the parts the Guardian may see when it is made, and opening it later needs the permission of every part it contains. A report belongs to the Guardian who got it: nobody else sees it. The Dependent cannot use these endpoints (`403 FORBIDDEN`).

## Endpoints
| Call | Result |
|---|---|
| `GET /dependents/{id}/reports/schedule` | `{dependent_id, frequency, since}`; `frequency: null` = off |
| `PUT /dependents/{id}/reports/schedule` body `{"frequency": "weekly" \| "monthly"}` | the schedule (200) |
| `DELETE /dependents/{id}/reports/schedule` | 204 (also when it was already off) |
| `POST /dependents/{id}/reports` body `{"days": 7..90}` (optional, default 7) | 201, one report (below) |
| `GET /dependents/{id}/reports?limit=20&offset=0` | `{items[], total, limit, offset}`, newest first, only my own |
| `GET /dependents/{id}/reports/{report_id}/download` | the PDF (`application/pdf`, attachment, not cached) |
| `DELETE /dependents/{id}/reports/{report_id}` | 204 |

A report:
```json
{
  "report_id": "uuid", "dependent_id": "uuid",
  "period": "weekly",            // weekly | monthly | custom
  "source": "scheduled",         // scheduled (made by the job) | manual
  "period_start": "2026-10-12", "period_end": "2026-10-18",   // local days (Asia/Karachi), both included
  "includes_adherence": true, "includes_vitals": true,
  "size_bytes": 4821, "created_at": "2026-10-19T00:01:05Z",
  "file_name": "humsafar-summary-2026-10-12-to-2026-10-18.pdf"
}
```

## How the automatic report works
- A Guardian switches it on **per Dependent and per Guardian** (`PUT .../reports/schedule`). Every Guardian chooses for themselves.
- The background job (every minute) makes the report of the **last finished period** once: `weekly` = the last Monday-to-Sunday week, `monthly` = the last calendar month. It is ready from the first minute after the period ends.
- A period that ended **before** the schedule was switched on is not made. Switching on a Wednesday gives the first weekly report on the next Monday. Changing the frequency starts a new schedule (`since` moves).
- When a scheduled report is ready the Guardian gets a **standard** notification: `type: "summary_report"`, title "Weekly summary is ready" / "Monthly summary is ready", body "<Dependent name>: 12 Oct 2026 to 18 Oct 2026.", and `data.report_id` (open the reports list or download directly). Reports made by `POST` do not send a notification.
- A schedule that has no permission left, a closed account, or a link that is no longer active makes nothing and does not fail.
- `POST .../reports` makes a report right now for the last `days` days, today included (`period: "custom"`, `source: "manual"`). Good for "send me one now" and for the demo.
- Limits: 60 reports per Guardian and Dependent (`409 REPORT_LIMIT`, delete old ones); reports older than 180 days are removed by the job.

## The PDF
Title "Weekly / Monthly / Custom health summary", the Dependent's name and the period. **Medicine adherence**: taken, missed, still waiting, the rate, how it compares with the period before, the streak, a table per medicine, and a day-by-day table. **Vitals**: a table with blood pressure, sugar, oxygen, temperature and heart rate (readings, average, lowest, highest, latest, and how the second half of the period compares with the first half). It shows numbers only: no "good", "bad" or "normal", and it ends with a note that it is not medical advice. Standard PDF fonts: characters outside Western European text (for example Urdu) show as "?" (same as the Medical Vault export, clarification 95).

## Errors
`403 FORBIDDEN` (Dependent), `403 NOT_LINKED_TO_DEPENDENT`, `403 MODULE_ACCESS_DENIED` (no permission for either part, or for a part the report contains), `404 REPORT_NOT_FOUND` (also another Guardian's report), `404 FILE_NOT_FOUND`, `500 FILE_UNREADABLE` (damaged stored file), `409 REPORT_LIMIT`, `422 VALIDATION_ERROR` (`days` outside 7..90, unknown `frequency`).

## For the screens (Talha / Sarim)
A "Reports" screen per Dependent (from the Analytics screen 16): a switch "Send me a report" with Weekly / Monthly / Off, a "Make a report now" button (7 / 14 / 30 days), and the list with a download button per row. The notification `summary_report` opens this list.
