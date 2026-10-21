# 0.7 — Low-fidelity wireframes (v0.1)

**Task:** 0.7 · **Owner:** Sarim · **Source file:** Figma *Humsafar – App Design*, page `01 · Wireframes (Low-Fi)`

Covers every screen in SDS §10.1, plus screens the API contracts in `docs/api/` require but SDS §10.1 does not list (marked —).

Conventions shown on every screen:
- Accessibility toggle (**Aa**) and language switcher (**EN|UR**) in the app bar (team UI convention).
- Guardian app bottom navigation: Home, Map, Chat, Vault, Analytics (SDS §10.2).
- Dependent Mode: three safety actions reachable in one tap from Home, large targets (FR-P1, NFR-07).
- Greyscale only. Colours, fonts and final layout come in the high-fidelity mockups (Tasks 1.12, 2.8, 3.9).

| # | Screen | Used by | Requirements | SDS §10.1 screen | File |
|---|---|---|---|---|---|
| 01 | Welcome | Guardian & Dependent | FR-A1 | Login / Registration | `Humsafar_Wireframe_01_Welcome_v0.1.png` |
| 02 | Log in | Guardian & Dependent | FR-A1 | Login / Registration | `Humsafar_Wireframe_02_Log_in_v0.1.png` |
| 03 | Create account | Guardian & Dependent | FR-A1 | Login / Registration | `Humsafar_Wireframe_03_Create_account_v0.1.png` |
| 04 | Verify identity (KYC) | Dependent | FR-A2 | Login / Registration (KYC) | `Humsafar_Wireframe_04_Verify_identity_(KYC)_v0.1.png` |
| 05 | Share my ID | Dependent | FR-B1 | — (from linkage contract) | `Humsafar_Wireframe_05_Share_my_ID_v0.1.png` |
| 06 | Guardian verification | Guardian | FR-A3 | Login / Registration (Guardian KYC) | `Humsafar_Wireframe_06_Guardian_verification_v0.1.png` |
| 07 | Guardian Dashboard | Guardian | FR-B4.2 | Guardian Dashboard | `Humsafar_Wireframe_07_Guardian_Dashboard_v0.1.png` |
| 08 | Alerts | Guardian | FR-M1, FR-M2, FR-D5 | — (from notification/escalation contracts) | `Humsafar_Wireframe_08_Alerts_v0.1.png` |
| 09 | Link a Dependent | Primary Guardian | FR-B1, FR-B2 | — (from linkage contract) | `Humsafar_Wireframe_09_Link_a_Dependent_v0.1.png` |
| 10 | Permissions | Primary Guardian | FR-A4 | Permission Management | `Humsafar_Wireframe_10_Permissions_v0.1.png` |
| 11 | Live Map | Guardian | FR-C1 – FR-C4 | Live Map | `Humsafar_Wireframe_11_Live_Map_v0.1.png` |
| 12 | Safe zone | Primary Guardian | FR-C2, FR-C3 | Live Map (geofence config, Task 2.8) | `Humsafar_Wireframe_12_Safe_zone_v0.1.png` |
| 13 | Care schedules | Guardian | FR-F1, FR-D4 | — (Guardian schedule config, Task 3.15) | `Humsafar_Wireframe_13_Care_schedules_v0.1.png` |
| 14 | Emergency settings | Primary Guardian | FR-D3, FR-R1 | — (remote alarm + external contact) | `Humsafar_Wireframe_14_Emergency_settings_v0.1.png` |
| 15 | Medical Vault | Guardian & Dependent | FR-G1 – FR-G4 | Medical Vault | `Humsafar_Wireframe_15_Medical_Vault_v0.1.png` |
| 16 | Analytics | Guardian | FR-Q1, FR-Q2 | Analytics Dashboard | `Humsafar_Wireframe_16_Analytics_v0.1.png` |
| 17 | Messages | Guardian & Dependent | FR-E1, FR-E2, FR-E4 | Communication | `Humsafar_Wireframe_17_Messages_v0.1.png` |
| 18 | Directory | Guardian & Dependent | FR-I1, FR-J1 | Directory / Marketplace | `Humsafar_Wireframe_18_Directory_v0.1.png` |
| 19 | Camera | Guardian | FR-K1, FR-K2 | Camera View | `Humsafar_Wireframe_19_Camera_v0.1.png` |
| 20 | Dependent Home | Dependent | FR-P1, FR-P2 | Dependent Mode — Home | `Humsafar_Wireframe_20_Dependent_Home_v0.1.png` |
| 21 | Panic | Dependent | FR-D2 | Dependent Mode — Panic | `Humsafar_Wireframe_21_Panic_v0.1.png` |
| 22 | Wellness check | Dependent | FR-D4 | Dependent Mode — Wellness Check | `Humsafar_Wireframe_22_Wellness_check_v0.1.png` |
| 23 | Medicine confirmation | Dependent | FR-F1.3 | Dependent Mode — Medication Confirmation | `Humsafar_Wireframe_23_Medicine_confirmation_v0.1.png` |
| 24 | Alarm ringing | Dependent | FR-D3 | — (Dependent side of FR-D3) | `Humsafar_Wireframe_24_Alarm_ringing_v0.1.png` |

**Overview:** `Humsafar_Wireframes_Overview_v0.1.png`

## Open points for Talha / Abdullah
- 05 *Share my ID*: the Dependent shows their ID / QR so the Primary can link them (linkage contract §3). Consent step is still an open security item (sds_clarifications item 9).
- 09 *Link a Dependent*: QR scanning needs a camera package in Flutter; typing the ID works without it.
- 16 *Analytics*: BP is manual entry only (team decision); wearable vitals depend on the band choice.
