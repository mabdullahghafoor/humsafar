# Design coverage check + missing screens (v0.1)

**Owner:** Sarim · **Date:** 21 Oct 2026 · **Figma:** page `02 · App Designs (Hi-Fi)`

Every functional requirement group in SRS v1.0 was compared with the 57 hi-fi screens on `dev` (and Figma). Six screens were missing, so they were designed here as v0.1, in the same style as the other sets.

## New screens in this folder

| # | Screen | App | Requirement | Backend today |
|---|---|---|---|---|
| 07b | Switch Dependent — sheet opened from "tap to switch" on Home (07); pick whose care you are viewing, or link another Dependent | Guardian | FR-B4 | Exists (linkage list, Task 1.5) |
| 16 | Analytics (**v0.3**, 22 Oct, matched to `analytics_contract.md`, Task 7.1) — 7 / 30 / 90 days; medicine taken: rate, taken / missed / waiting, a bar per day, change vs the period before, full days in a row ("No data yet" instead of 0 %); vitals per metric with average, latest and trend wording (Going up / Going down / Steady / Not enough readings yet), numbers only; link to Summary reports. The wellness-check card is removed (not part of FR-Q1 or the contract) | Guardian | FR-Q1 | Built (Task 7.1) |
| 16b | **Summary reports** (new, v0.2, `reports_contract.md`, Task 7.2) — Off / Weekly / Monthly per Guardian, make one now (7 / 14 / 30 days), my reports with PDF download; only my own; parts without permission left out | Guardian | FR-Q2 | Built (Task 7.2) |
| 30 | Settings — profile and Verified status, language, large text, notifications, audit log, permissions, about, **Log out**, Close my account | Guardian | FR-P2, FR-P4, FR-N3, FR-O1 | Profile from `GET /auth/me`; log out = delete tokens on the phone (no server logout, `auth_contract.md`) |
| 30b | Close my account (**v0.2**, `account_contract.md`, Task 6.7) — reopen for 60 days, signed out everywhere, links end; a Primary with an active Dependent must close the Dependent first (`409 CLOSE_DEPENDENTS_FIRST`); password only | Guardian | FR-O1 | Built (Task 6.7) |
| 30c | **Close Dependent** (new, v0.2) — Primary only; Dependent signed out, every Guardian loses access, doctor links stop, open alerts closed, data deleted after 60 days; reopen within 60 days | Guardian | FR-O1 | Built (Task 6.7) |
| 31 | Audit log (**v0.2**, `audit_contract.md`, Task 6.6) — newest first, the server's readable `label` + who did it + time, filters Who (actor) and When (period); Primary only, read-only; messages, locations and band readings are not listed | Guardian | FR-N3 | Built (Task 6.6) |
| 32 | My settings — big Language and Text size buttons, Show my ID (opens 05), who looks after me, log out with confirmation | Dependent | FR-P1, FR-P2, FR-P4 | Exists (`/auth/me`, linkage) |

Files: `Humsafar_Design_<number>_<Screen>_v<version>.png` (07b, 30, 32 are v0.2 after the colour update; 16 is v0.3; 16b, 30b, 30c, 31 are v0.2) and `Humsafar_Design_Coverage_Overview_v0.3.png` (rebuilt from the latest versions).

## Coverage matrix (SRS v1.0 → screens)

| Requirement | Screens | Status |
|---|---|---|
| FR-A1 Registration, Guardian hierarchy | 01, 02, 03 | Covered |
| FR-A2 Dependent KYC | 04 | Covered |
| FR-A3 Guardian verification | 06 | Covered |
| FR-A4 Permission dashboard | 10, 15e, 17g | Covered |
| FR-B1 Linkage | 05, 09 | Covered |
| FR-B2 Guardian cap | 10 ("1 left") | Covered |
| FR-B4 Several Dependents per Guardian | 07, **07b** | Covered now |
| FR-C1 Location tracking | 11, 11b, Dependent home banner | Covered |
| FR-C2, C3 Safe zones and alerts | 11b, 12, 12b | Covered |
| FR-C4 Location history | 11c | Covered |
| FR-D1 Missed dose | 08b | Covered |
| FR-D2 Panic | 20, 21, 21b, 07 | Covered |
| FR-D3 Remote alarm | 14, 24 | Covered |
| FR-D4 Wellness check | 13b, 22 | Covered |
| FR-D5 Escalation chain | 08 | Covered |
| FR-D6 Fall detection (Optional) | — | Not designed: optional and not on the roadmap; a "possible fall" alert would reuse 08 |
| FR-R1 External emergency contact | 14 | Covered |
| FR-L1, L2 Battery and connection | 07, 11 | Covered |
| FR-E1 Text messages | 17, 17b, 25, 25b | Covered |
| FR-E2 Calls | 17d, 17e, 17f, 25d | Covered |
| FR-E4 Urgent voice messages | 17c, 25c | Covered |
| FR-E5 Bridge call (Optional) | — | Not designed: optional / stretch |
| FR-M1, M2 Notifications and "seen" | 08 | Covered |
| FR-F1 Medicine schedule and two-step confirm | 13, 23, 23b | Covered |
| FR-G1 Vault and export | 15, 15b, 15c | Covered |
| FR-G2 Record types per Secondary | 15e | Covered |
| FR-G3 Doctor link | 15f | Covered |
| FR-G4 Appointments | 15d | Covered |
| FR-H1 Manual vitals | 26, 26b, 28 | Covered (re-check after Task 5.3) |
| FR-H2 Band | 27, 27b | Covered (re-check after Task 5.4) |
| FR-I1 Directory | 18 | Covered |
| FR-J1 Home care requests | 18b, 18c | Covered |
| FR-I2/J2 Activity log | 18d | Covered |
| FR-K1 Camera and viewing notice | 19, 19c, 29, 29b | Covered |
| FR-K2 Event clips | 19b | Covered |
| FR-N1, N2 Encryption | — | No screen needed |
| FR-N3 Audit log, viewable by the Primary | **31** | Covered now |
| FR-O1 Data retention and deletion | 19b note, 30b, 30c | Covered |
| FR-P1 Dependent Mode | 20–25d, 28, 29, **32** | Covered |
| FR-P2 Large text and high contrast | Aa on every screen, **30**, **32** | Covered |
| FR-P4 Urdu | EN\|UR on every screen, UI text sheet, **30**, **32** | Covered |
| FR-Q1 Analytics | **16** | Covered now |
| FR-Q2 Summary reports (Optional) | 16b | Covered (built in Task 7.2) |
| (not in SRS) Settings, log out, profile | **30**, **32** | Covered now |

## Open points
1. ✅ **Close account** is built (Task 6.7). A Primary must close the Dependent first, so the "who becomes Primary" question does not arise (clarification 159).
2. ✅ **Audit log (31)** matches Task 6.6. The action text comes from the server in English (`label`); the app translates it by `action` name.
3. ✅ **Analytics (16)** and **Summary reports (16b)** match Tasks 7.1 and 7.2.
4. **How the Dependent reaches My settings (32):** suggested from the "More" link on Home (20); no gear icon, to keep the Dependent home simple.
5. Urdu is shown as "Urdu" in the language buttons of 32 only because the PNG export has no Urdu font; in the app the button says اردو.

## Colour update (30 Oct 2026)
All screens in this folder now use the **style guide v0.2 colours**: old red `#DC2626` → `#B91C1C` and old grey `#64748B` → `#475569` (NFR-08 contrast fix). **Colours only, no layout or text change.** Updated screens:

| # | Screen | Version |
|---|---|---|
| 07b | Switch Dependent | v0.1 → **v0.2** |
| 30 | Settings | v0.1 → **v0.2** |
| 32 | My settings | v0.1 → **v0.2** |

Overview rebuilt from the latest versions: v0.2 → **v0.3**. Editable SVG sources of every screen in this folder are in `svg/` (same names as the PNGs, `.svg`); use them for Figma import.
