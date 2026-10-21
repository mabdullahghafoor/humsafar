# design/ — Screen designs

**Owner:** Sarim

The working design lives in Figma (file: *Humsafar – App Design*). This folder holds exported snapshots (PNG) for each task, so the repo has a record of what each screen was built from. Each subfolder has its own README that maps the screens to the SRS requirements and API contracts.

**Contents**

| Folder | Task | What is in it | For Talha's task |
|---|---|---|---|
| `0.7_wireframes/` | 0.7 | Low-fidelity wireframes, 24 screens (v0.1) | reference only |
| `1.12_identity_access/` | 1.12 | Welcome, log in, create account, KYC, share ID, verify account, link a Dependent, permissions + style guide (v0.1) | 1.8–1.11, 2.5 |
| `2.8_map_geofence/` | 2.8 | Live Map, location history, safe zones, edit safe zone (v0.1) | 2.6 |
| `3.9_safety_screens/` | 3.9 | Dependent Mode (home, panic, wellness check, medicine time, alarm) + Guardian home, alerts, care schedules, emergency settings (v0.1) | 3.10–3.15 |
| `4.9_communication/` | 4.9 | Messages, chat, urgent voice, calls (Guardian and Dependent) (v0.1) | 4.6–4.8 |
| `5.9_records_vitals_band/` | 5.9 | Medical vault, add record, export, appointments, record access, doctor links, vitals, my health, band (v0.2, matched to `records_contract.md` and `appointment_contract.md`) | 5.6–5.8 |
| `6.11_directory_camera/` | 6.11 | Directory, home care, request a visit, activity log, camera screens (v0.1) | 6.8–6.10 |
| `coverage/` | — | Design coverage check (every SRS requirement → screen) + 6 screens that were missing: 07b Switch Dependent, 16 Analytics, 30 Settings, 30b Close account, 31 Audit log, 32 My settings (v0.1) | 7.3 and later |
| `ui_text/` | — | All fixed screen text in English and Urdu with suggested localisation keys (v0.4, 558 lines) | 7.4 |

**File naming:** `Humsafar_Design_<number>_<Screen>_v<version>.png`, e.g. `Humsafar_Design_15f_Doctor_links_v0.2.png`. Screen numbers match the Figma frame names (page *02 · App Designs (Hi-Fi)*).

**Figma file:** https://www.figma.com/design/fpY8fd72McW3iVS0PydHtw/Humsafar-App-Design (view access: Abdullah, Talha)
