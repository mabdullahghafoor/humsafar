# Design coverage check + missing screens (v0.1)

**Owner:** Sarim · **Date:** 21 Oct 2026 · **Figma:** page `02 · App Designs (Hi-Fi)`

Every functional requirement group in SRS v1.0 was compared with the 57 hi-fi screens on `dev` (and Figma). Six screens were missing, so they were designed here as v0.1, in the same style as the other sets.

## New screens in this folder

| # | Screen | App | Requirement | Backend today |
|---|---|---|---|---|
| 07b | Switch Dependent — sheet opened from "tap to switch" on Home (07); pick whose care you are viewing, or link another Dependent | Guardian | FR-B4 | Exists (linkage list, Task 1.5) |
| 16 | Analytics — medicine on time per day, wellness checks answered, vitals trend (normal range in green), 7 / 30 days; weekly PDF report marked "later" | Guardian | FR-Q1 (FR-Q2 optional) | Not yet (Task 7.1) |
| 30 | Settings — profile and Verified status, language, large text, notifications, audit log, permissions, about, **Log out**, Close my account | Guardian | FR-P2, FR-P4, FR-N3, FR-O1 | Profile from `GET /auth/me`; log out = delete tokens on the phone (no server logout, `auth_contract.md`) |
| 30b | Close account — what happens (60-day delete or anonymise), type CLOSE + password | Guardian | FR-O1 | **No endpoint planned** (see open points) |
| 31 | Audit log — permission changes, camera viewing, record access and export, filter by type; Primary only, read-only | Guardian | FR-N3 | Rows are written today; reading them comes with Task 6.6 |
| 32 | My settings — big Language and Text size buttons, Show my ID (opens 05), who looks after me, log out with confirmation | Dependent | FR-P1, FR-P2, FR-P4 | Exists (`/auth/me`, linkage) |

Files: `Humsafar_Design_<number>_<Screen>_v0.1.png` and `Humsafar_Design_Coverage_Overview_v0.1.png`.

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
| FR-O1 Data retention and deletion | 19b note, **30b** | Covered now |
| FR-P1 Dependent Mode | 20–25d, 28, 29, **32** | Covered |
| FR-P2 Large text and high contrast | Aa on every screen, **30**, **32** | Covered |
| FR-P4 Urdu | EN\|UR on every screen, UI text sheet, **30**, **32** | Covered |
| FR-Q1 Analytics | **16** | Covered now |
| FR-Q2 Summary reports (Optional) | row in 16 | Marked "later" |
| (not in SRS) Settings, log out, profile | **30**, **32** | Covered now |

## Open points
1. **Close account (30b) has no endpoint and no task in the roadmap.** FR-O1 talks about "account closure", so the team needs to decide: build it, or record it as future work. Also: if a Primary Guardian closes their account, who becomes Primary? (Same gap as clarification 12, "no way to remove a Guardian".) To be added to the drift register at its next update.
2. **Audit log (31)** can be built after Abdullah's Task 6.6 (audit logging). The rows already exist.
3. **Analytics (16)** waits for Task 7.1 (analytics endpoints).
4. **How the Dependent reaches My settings (32):** suggested from the "More" link on Home (20); no gear icon, to keep the Dependent home simple.
5. Urdu is shown as "Urdu" in the language buttons of 32 only because the PNG export has no Urdu font; in the app the button says اردو.
