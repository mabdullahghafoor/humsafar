# 5.9 — High-fidelity mockups: medical vault, appointments, vitals, wearable band (v0.1)

**Task:** 5.9 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`, sections Guardian App and Dependent App. Same style as 1.12 / 3.9 / 2.8 / 4.9. For Talha's Tasks **5.6** (records UI), **5.7** (vitals entry UI) and **5.8** (wearable pairing UI).

**Built from:** SRS v1.0 §4.4 (FR-G1–G4, FR-H1, FR-H2) and the database tables already in migration 0001 (`medical_records`, `appointments`, `vital_readings` with `source` = manual / wearable, `wearable_devices`). The Phase 5 API contracts did not exist yet when these were drawn. **If an endpoint differs, the screens will be updated to match it (v0.2).**

## Guardian app

| # | Screen | Requirements |
|---|---|---|
| 15 | Medical Vault — records list, type filter, who added it, Export PDF | FR-G1 |
| 15b | Add record — type (Prescription / Lab report / X-ray & scan / Other), title, date, take photo or upload | FR-G1 |
| 15c | Export records — complete history / one year / one month, optional vitals report, optional doctor link (72 h) | FR-G1, FR-H1, FR-G3 (optional) |
| 15d | Appointments — next visit card, later list, reminders to both sides | FR-G4 |
| 15e | Record access (Primary only) — per Secondary, which record types they can see | FR-G2 |
| 26 | Vitals — 7-day blood pressure chart, sugar, SpO2, temperature, heart rate from the band | FR-H1, FR-H2 |
| 26b | Add reading — pick the measurement, big number fields | FR-H1 |

## Dependent app

| # | Screen | Requirements |
|---|---|---|
| 28 | My health — next doctor visit, big "Add my blood pressure / sugar", band status, my records | FR-P1, FR-G4, FR-H1 |
| 27 | My band — connected, last sync, heart rate, steps, Sync now (band battery is shown by 3 lights on the band, not in the app) | FR-H2 |
| 27b | Connect band — scanning, bands found, Connect | FR-H2 |

## Notes for Talha
- **Record types** on screen map to `medical_records.type`. The four types are a design proposal; use whatever list the backend fixes.
- **Who added it** comes from `uploaded_by`; vitals show **Manual** or **Band** from `vital_readings.source`.
- **Blood pressure is always typed in by hand** (the band does not measure it; FR-H1 decision).
- **Band data never raises an alarm by itself** (FR-H2: not a sole crisis trigger). The screens only show it.
- **Band disconnected / out of range** must not block anything else (FR-H2): show a grey "Not connected · last sync …" instead of the green chip on 27 and 28.
- **15e** is only shown to the Primary, and only matters for a Secondary who already has the Health Records permission.
- The band's name (Band 7A2F) is a placeholder until the band is chosen (5.11).
- **Band battery is not shown in the app** (team decision 19 Oct, at the band maker's shop): the band shows it with 3 LEDs. Screen 27 only reminds the user to look at the lights. Can be added later if the supervisor asks.

## Design choices open to discussion
1. **"Above usual" chip** on blood pressure (amber). The SRS sets no alert rule for vitals, so this is display only; the green band on the chart is a placeholder normal range. Remove it if the team prefers no judgement on screen.
2. **Units:** temperature in °F (common in Pakistan), sugar in mg/dL. Could follow the EN|UR / settings choice.
3. **Doctor link (FR-G3)** is Optional in the SRS; the section can be hidden if it is not built.
4. **Reminder times** for appointments (1 day and 2 hours before) are a suggestion.
5. Steps are shown because the SRS mentions activity / step count; they can be dropped if the chosen band does not send them.
