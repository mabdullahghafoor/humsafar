# 5.9 — High-fidelity mockups: medical vault, appointments, vitals, wearable band (v0.2 / v0.3)

**Task:** 5.9 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`, sections Guardian App and Dependent App. Same style as 1.12 / 3.9 / 2.8 / 4.9. For Talha's Tasks **5.6** (records UI), **5.7** (vitals entry UI) and **5.8** (wearable pairing UI).

**Built from:** SRS v1.0 §4.4 (FR-G1–G4, FR-H1, FR-H2). **v0.2 (20 Oct): vault, export, doctor link and appointments now match Abdullah's `docs/api/records_contract.md` and `appointment_contract.md` (Task 5.1, PR #47).** **v0.3 (21 Oct): 15c, 26, 26b, 27 and the new 26c match `vitals_contract.md` (Task 5.3, PR #58) and `wearable_contract.md` (Task 5.4, PR #59), and use the style guide v0.2 colours.** 15, 15b, 15d, 15e, 15f, 27b and 28 stay v0.2 (no change needed). 16 Analytics (in `docs/design/coverage/`) is updated to v0.2 for the same "no medical advice" rule.

## What changed in v0.3
- **No judgement on screen:** the "Above usual" chip and the green "normal range" on the charts are removed (26 and 16 Analytics). The server never says high, low or normal (no medical advice); 26 says "Numbers only. Ask the doctor what they mean."
- **Fixed units:** sugar in mg/dL, temperature in **°C** (was °F). People may type mmol/L or °F; the server converts and the app always shows mg/dL and °C (26b explains it).
- 26b: "Top number / Bottom number" instead of systolic / diastolic; "When measured" (`recorded_at`, not in the future, up to 365 days back).
- 15c Export: **Add vitals** is now real (`include_vitals`): typed readings listed, band readings one line per day; the doctor link includes vitals when ticked.
- 27 My band: status **Receiving data / Last reading** (from `status` and `last_data_at`); **steps removed** (the band does not send them yet); second tile is SpO2 "if your band has it".
- **New 26c Band not sending (Guardian):** the standard `band_no_data` notice after 30 minutes without new data; it closes by itself and never escalates; nothing else is blocked.

## What changed in v0.2
- 15b Add record: **Note (optional)** field; a record needs a file, a note, or both; files PDF / JPG / PNG **up to 10 MB**.
- 15c Export: vitals report marked as coming with Task 5.3 (the export endpoint has no vitals yet); doctor link opens with **no login**, 72 hours by default.
- **New 15f Doctor links:** the link is shown once (Share / Copy), with its expiry; list of all links with Active / Expired / Cancelled and how often each was opened; Cancel. Up to 10 open links.
- 15d Appointments: **Upcoming / History** tabs (cancelled appointments stay in History); reminders **24 hours and 1 hour** before (was 1 day and 2 hours).

## Guardian app

| # | Screen | Requirements |
|---|---|---|
| 15 | Medical Vault — records list, type filter, who added it, Export PDF | FR-G1 |
| 15b | Add record — type (Prescription / Lab report / X-ray & scan / Other), title, date, take photo or upload | FR-G1 |
| 15c | Export records — complete history / one year / one month, vitals report (with 5.3), doctor link (72 h) | FR-G1, FR-H1, FR-G3 |
| 15f | Doctor links — new link (shown once), expiry, Share / Copy, all links with status and Cancel | FR-G3 |
| 15d | Appointments — Upcoming / History, next visit card, reminders 24 h and 1 h before to both sides | FR-G4 |
| 15e | Record access (Primary only) — per Secondary, which record types they can see | FR-G2 |
| 26 | Vitals — 7-day blood pressure chart, sugar, SpO2, temperature, heart rate from the band | FR-H1, FR-H2 |
| 26b | Add reading — pick the measurement, big number fields, units note | FR-H1 |
| 26c | Band not sending — no new band data for 30 min, what to do (v0.3) | FR-H2 |

## Dependent app

| # | Screen | Requirements |
|---|---|---|
| 28 | My health — next doctor visit, big "Add my blood pressure / sugar", band status, my records | FR-P1, FR-G4, FR-H1 |
| 27 | My band — Receiving data, last reading, heart rate, SpO2 if the band has it, Sync now (band battery is shown by 3 lights on the band, not in the app) | FR-H2 |
| 27b | Connect band — scanning, bands found, Connect | FR-H2 |

## Notes for Talha
- **Record types** map to the contract's `category`: `prescription`, `lab_report`, `xray`, `other`.
- Show **edit / delete** only when the record's `can_modify` is true (the person who added it, or the Primary).
- Create the upload's `client_id` once per record and reuse it on retry (`already_saved: true` = it arrived the first time).
- Doctor link: if the returned `url` starts with `/`, put the server address in front before sharing.
- Known limit: Urdu text in a record's title or note shows as `?` inside the exported PDF (the app shows it correctly).
- **Who added it** comes from `uploaded_by`; vitals show **Typed** or **Band** from the reading's `source` (`manual` / `wearable`).
- **Blood pressure is always typed in by hand** (the band does not measure it; FR-H1 decision).
- **Band data never raises an alarm by itself** (FR-H2: not a sole crisis trigger). The screens only show it.
- **Band disconnected / out of range** must not block anything else (FR-H2): show a grey "Not connected · last sync …" instead of the green chip on 27 and 28.
- **15e** is only shown to the Primary, and only matters for a Secondary who already has the Health Records permission.
- The band's name (Band 7A2F) is a placeholder until the band is chosen (5.11).
- **Band battery is not shown in the app** (team decision 19 Oct, at the band maker's shop): the band shows it with 3 LEDs. Screen 27 only reminds the user to look at the lights. Can be added later if the supervisor asks.

## Design choices open to discussion
1. ~~"Above usual" chip~~ removed in v0.3 (no medical advice, vitals contract).
2. ~~Units~~ settled by the contract: mg/dL and °C shown; mmol/L and °F accepted when typing.
3. **Doctor link (FR-G3)** is now built by the backend (Task 5.1).
4. ~~Reminder times~~ settled by the contract: 24 hours and 1 hour before.
5. ~~Steps~~ removed in v0.3: the band does not send steps until the sensor list is known (clarification 89).

## Colour update (30 Oct 2026)
All screens in this folder now use the **style guide v0.2 colours**: old red `#DC2626` → `#B91C1C` and old grey `#64748B` → `#475569` (NFR-08 contrast fix). **Colours only, no layout or text change.** Updated screens:

| # | Screen | Version |
|---|---|---|
| 15 | Medical Vault | v0.2 → **v0.3** |
| 15b | Add record | v0.2 → **v0.3** |
| 15d | Appointments | v0.2 → **v0.3** |
| 15e | Record access | v0.2 → **v0.3** |
| 15f | Doctor links | v0.2 → **v0.3** |
| 27b | Connect band | v0.2 → **v0.3** |
| 28 | My health | v0.2 → **v0.3** |

Overview rebuilt from the latest versions: v0.3 → **v0.4**. Editable SVG sources of every screen in this folder are in `svg/` (same names as the PNGs, `.svg`); use them for Figma import.
