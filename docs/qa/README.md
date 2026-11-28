# qa/ — Quality assurance

**Owner:** Sarim

**Folders.** Test cases and plans are written before a build exists, backend and design checks do not use the app, and every app result belongs to the APK build it was run on. So:

| Folder | What goes in it |
|---|---|
| `test-cases/` | Test cases, test plans and the checklist template (no build) |
| `results/backend/` | Backend results: Postman runs, security review and its Postman collection |
| `results/design/` | Design checks (contrast) |
| `results/security/<build>/` | Security review run on that build (code review, scans, APK scan, live checks). **Every new build gets its own security folder** and a retest of the open findings |
| `results/debug-apk-<version>/` | Every result run on that APK build. **A new build gets its own folder** (e.g. `debug-apk-1.9/`); a run that spanned several builds goes under the last one, and its row says which builds |

**Finding codes:** F- ICP runs and general app findings, N- 3.16 accessibility, G- 6.12 directory, P- 5.10 records / vitals, SEC- security review (SEC-01 to SEC-05 are the 6.13 v0.3 findings F-01 to F-05 renamed), UI- design vs app (layout and detail of a built screen against its mockup); numbers never repeat. Every finding and retest names the APK it was found or checked on.

## Test cases and plans

`test-cases/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Checklist_Template_v1.0.pdf` | 1.13 | Reusable checklist |
| `Humsafar_QA_3.16_Accessibility_Test_Cases_v0.1.pdf` | 3.16 | Accessibility of Dependent Mode: 2 taps (NFR-07), large text and contrast (NFR-08), touch targets, Urdu; written ahead, run waits for Talha's 3.11–3.13 |
| `Humsafar_QA_3.17_Escalation_Test_Cases_v1.0.pdf` | 3.17 | Escalation chain cases + ICP-3 live script |
| `Humsafar_QA_4.10_Messaging_Calls_Test_Cases_v1.0.pdf` | 4.10 | Messaging, urgent voice and calls cases + ICP-4 live script |
| `Humsafar_QA_5.10_Records_Vitals_Test_Cases_v0.4.pdf` | 5.10 | Records, record categories per Secondary, appointments, vitals and band (mock data) from the 5.1–5.4 contracts; two real-band cases wait for 5.5 |
| `Humsafar_QA_6.12_Camera_Directory_Test_Cases_v0.4.pdf` | 6.12 | Camera live view and viewing notice (K-01–K-11) and emergency clips (K-12–K-17) from the 6.3 / 6.4 contract; directory (D-01–D-08) and requests / Activity Timeline (D-09–D-18) |
| `Humsafar_QA_8.1_E2E_Test_Plan_v0.3.pdf` | 8.1 | End-to-end test plan draft (v0.3: all 22 use cases now have their backend, Tasks 6.2–7.2) |

## Backend

`results/backend/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Phase1_Results_v1.0.pdf` | 2.9 | Phase 1 QA results (Postman run + functional / security checks) |
| `Humsafar_QA_Backend_Regression_Phases1-7_Results_v2.0.pdf` | 7.7 | QA regression pass of the whole backend, Phases 1–7 (Tasks 1.3–7.2): full Postman collection, 30 folders, 949 requests, 1501 / 1501 checks passed, 0 product bugs (22 Oct 2026, dev 7467459). Replaces v1.0 (Phases 1–6.1) |
| `Humsafar_QA_6.13_Security_Review_v0.3.pdf` | 6.13 | Security review checklist from SDS 17 and the 6.5 security guide: 29 checks (14 pass by code review, 5 passed in Postman runs: 7.7 run 22 Oct + hand checks S-09 / S-12 on the hosted server 30 Oct, 4 still to run: S-04 device, S-16 4-viewer limit, S-15 / S-26 with Abdullah), 5 findings (1 High resolved: app privacy notice field names; 2 Medium: no end-to-end A/V, host disk encryption) |
| `Humsafar_QA_6.13_Hand_Checks.postman_collection.json` | 6.13 | Postman collection for the hand checks S-09 (wrong phone codes → 429) and S-12 (camera stream token not cached); makes its own random test accounts. Run with base_url set to the hosted server or a local backend |
| `Humsafar_QA_Permission_Checks_v1.0.pdf` | 5.10, 6.12, 4.10 | Secondary Guardian permission checks through /docs (9 Nov): **15 / 15 PASS, no new finding**. Sara / Bilal on vault, record categories, doctor links, vitals, visit requests, notices and messages; audit rows for hide / show. Second pass of the cases not run in the 5.10, 6.12 and 4.10 v1.0 reports |

## Security

`results/security/`

| Build | File | Task | Status |
|---|---|---|---|
| debug-apk-1.9.1 | `debug-apk-1.9.1/Humsafar_QA_Security_Review_debug-apk-1.9.1_v1.0.pdf` | 6.13 | Security review v1.0 (22 Nov), follows 6.13 v0.3: **67 checks** (SDS 17, OWASP API Top 10, OWASP MASVS): 32 pass, 20 with a finding, 7 notes, 7 still to run (S-04, S-67 device; S-15, S-26, S-38 Abdullah; S-16 4 viewers; S-52 app library scan). **0 Critical / High open; 9 Medium, 12 Low.** Medium: no server logout and reusable refresh token (SEC-06), no password change (SEC-07), cleartext allowed (SEC-08), mock phone code 123456 (SEC-09), public API docs (SEC-10), 141 known library vulnerabilities (SEC-20), debug APK with readable source (SEC-21), plus SEC-02 / SEC-03 from v0.3 |
| (code audit) | `code-audit-2026-11-23/Humsafar_QA_Security_Code_Audit_2026-11-23_v1.0.pdf` | 6.13 | Source-code audit of the backend and the Flutter app, no APK tested (23 Nov): 14 backend checks, 10 Flutter checks, cross-check and one priority list. Proposed new findings SEC-23 to SEC-31. See the README in that folder |
| debug-apk-1.9.4 | `debug-apk-1.9.4/Humsafar_QA_Security_Retest_debug-apk-1.9.4_v1.0.pdf` | 6.13 | Security retest (25 Nov), code review plus phone checks, not an APK scan: SEC-10 verified, SEC-14 fixed in code, SEC-15 verified on Medical Vault and Vitals, SEC-08 holds in release builds only, SEC-19 and SEC-21 not done. **New F-32 (Medium):** developer role-switch icon visible on both Home screens. SEC-23 noted |
| debug-apk-1.9.5 | `debug-apk-1.9.5/Humsafar_QA_Security_Retest_debug-apk-1.9.5_v1.0.pdf` | 6.13 | Security retest (26 Nov): 2 verified or fixed, 4 partly fixed, 1 not verifiable on a debug APK (F-32: fixed in code with `kDebugMode`), 1 still open (SEC-22). A signed release APK is needed to check F-32, SEC-08, SEC-19 and SEC-21 |
| debug-apk-1.9.5 | `debug-apk-1.9.5/Humsafar_QA_Security_Library_Scan_debug-apk-1.9.5_v1.1.pdf` | 6.13 | Library scan S-52 (27 Nov): osv-scanner 2.7.1 on Talha's `pubspec.lock` at commit 1908ada, **236 packages, 0 known vulnerabilities**, no new finding. Limits: Dart libraries only (no Gradle or native SDKs) and thin Dart coverage in the database. **v1.1 (28 Nov):** corrects v1.0, which wrongly said the band libraries were not scanned (they are in the lockfile); the 1.9.6 lockfile is identical, so the result also applies to 1.9.6 |

**Security folders by build.** The security review started on `debug-apk-1.9.1` (22 Nov), so earlier builds (1.7 to 1.9) have no security report. `debug-apk-1.9.2` could not log in and `debug-apk-1.9.3` only had its SEC-10 check done inside the functional retest, so neither has a security folder.

## Design

`results/design/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_NFR-08_Contrast_Check_v1.0.pdf` | 3.16 (prep) | Colour contrast of the style guide, all hi-fi screens and the app's colours against WCAG AA; two token fixes |

## debug-apk-1.7 (ICP-1 ran on 1.4–1.7)

`results/debug-apk-1.7/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_ICP1_Results_v1.1.pdf` | ICP-1 (1.13) | Identity & Access run 26–29 Oct with Abdullah and Talha on debug-apk-1.4 to 1.7: 22 / 23 PASS, 0 FAIL, signed off by Abdullah (PRs #84–#86). Findings F-01–F-09; F-03, F-05, F-09 verified on 1.8 (see the 1.8 retest); F-04, F-07, F-08 still open |
| `Humsafar_QA_3.16_Accessibility_Results_v1.0.pdf` | 3.16 | Accessibility audit on a real phone (debug-apk-1.7, 30 Oct): 20 / 27 PASS, 4 partial, 1 FAIL (large text not remembered), 2 blocked (medicine cannot be added, High). 14 findings (1 High, 6 Medium, 7 Low) for Talha's 7.5 |
| `Humsafar_QA_6.12_Directory_Results_v1.0.pdf` | 6.12 | Directory half run on a real phone (debug-apk-1.7, 30 Oct): 8 / 18 PASS, 2 partial, 1 FAIL, 3 blocked, 4 not run. Critical G-01: the app's client_id is not a UUID, so visit requests, text / voice messages, new records and vitals readings all fail (fix in 1.8). Camera half waits for the camera phone (6.10) |

## debug-apk-1.8

`results/debug-apk-1.8/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_ICP3_Results_v1.1.pdf` | ICP-3 (3.17) | Run 1 split run (4 Nov) + Run 2 on two phones by Sarim (7 Nov, debug-apk-1.8, normal timers): 8 PASS, 2 partial, 1 FAIL (Remote Alarm never rings), 1 skipped. SMS to the emergency contact proven (5 min 39 s). **Not passed yet: F-16 Critical (backend) — the server sends no real push to any phone.** Also F-10, F-13 High; F-12, F-14, F-15 Medium; F-11, F-17, F-18 Low (frontend). Replaces v1.0 |
| `Humsafar_QA_Retest_debug-apk-1.8_v1.0.pdf` | ICP-1, 3.16, 6.12 | Retest of the open items on debug-apk-1.8 (30 Oct, 7 Nov): G-01, N-01, G-02, F-03, F-05, F-09 Verified; A-04, D-09–D-11, D-13, D-16, KYC resume, bottom sheets PASS; back swipe on the signed-in Home closes the app (F-19, Low); A-05 blocked by real push; D-12, D-14, D-17 not run. New Low findings F-19, N-15. Updates ICP-1 v1.1, 3.16 v1.0, 6.12 v1.0 |
| `Humsafar_QA_4.10_Messaging_Results_v1.0.pdf` | 4.10 / ICP-4 | Messaging half on two phones (debug-apk-1.8, 7 Nov): 7 / 9 PASS, 2 partial (no notification, ICP-3 F-16), no new finding. Calls blocked until real push (F-16) |
| `Humsafar_QA_Push_Check_debug-apk-1.8_v1.0.pdf` | ICP-3 F-16, 4.10 | Real push on debug-apk-1.8 (9 Nov): **F-16 fixed on the server** (Panic, closed notice, alarm and message arrive in 1–2 s with the app closed). App findings: **F-25 High** calls cannot start (`receiver_id` instead of `callee_id`), F-13 alarm does not ring, F-23 Panic plays the normal sound, F-24 notification tap lands on Home |

## debug-apk-1.9

`results/debug-apk-1.9/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9_v0.1.pdf` | Retest of 1.8 findings | **Blocked** (8–9 Nov): the build cannot reach the server on either phone (F-22, Critical: most likely built without the hosted API_BASE_URL); raw error text shown (F-21, Low). No check could run; the full retest on the rebuilt APK becomes v1.0 |

## debug-apk-1.9.1

`results/debug-apk-1.9.1/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.1_v1.0.pdf` | Retest of Talha's 1.9 / 1.9.1 list | 9 Nov: **23 verified** (F-22, F-25, F-20, the 5.10 P- items, G-03, G-04, N-02/03/06/07/12/14, F-10, F-12, F-15, F-19 …); still open F-13, F-17, F-18, F-04 partly. **New: F-29 High** an incoming call can never be answered (ICP-4 calls blocked); **F-26 High (backend / hosting)** uploaded files lost on every redeploy; F-27, F-28 Medium; F-30, N-16 Low |
| `Humsafar_QA_Design_vs_App_debug-apk-1.9.1_v1.0.pdf` | Design vs app | 22 Nov: 10 screens compared side by side with the mockups (screenshots from Sarim's phone): the app does what the design says, but the look is far from it. **13 findings UI-01 to UI-13: 4 High, 7 Medium, 2 Low.** High: app opens on the Dev Role Switcher, no splash / logo (UI-01); Home has no per-Dependent status, quick actions or bottom bar (UI-03, **team decision**); Live Map shows the email and raw minutes (UI-09); test data on every screen (UI-13). 2 team decisions (Home model, top bar), 1 design change (Notices tab). Remaining screens follow on the next build |
| `Humsafar_QA_5.10_Records_Vitals_Results_v1.1.pdf` | 5.10 / ICP-5 | 27 Nov, brings together the 7 Nov first pass (debug-apk-1.8), the 9 Nov retest and the 9 Nov permission checks (replaces v1.0): **32 / 33 PASS, 1 partial, 0 FAIL**. P-01, P-02, P-03, P-05–P-07 and F-20 verified on 1.9.1; 15 / 15 Secondary permission checks pass. **Not signed off:** F-26 (files lost on redeploy) open, 25 cases not run, band cases wait for the real band. No new test run |

## debug-apk-1.9.2

`results/debug-apk-1.9.2/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.2_v0.1.pdf` | Retest of Talha's 1.9.2 list | **Blocked** (23 Nov): Login fails on both phones with "Can't reach the server" while the hosted server answers in the browser (**F-31, Critical**, same symptom as F-22). Passed: Splash, Launch and Welcome open first (UI-01, F-07 look closed), app name "Humsafar" (F-30), v2.0 splash, friendly connection message (F-21). New: UI-14 (Low) Launch screen layout. Becomes v1.0 on the next build |

## debug-apk-1.9.3

`results/debug-apk-1.9.3/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.3_v1.0.pdf` | Retest of Talha's 1.9.3 list | 23 to 25 Nov: F-31 fixed (login works on the hosted server; the fix was the build command only), database move to `humsafar-db-2` confirmed, SEC-10 verified (`/docs`, `/redoc`, `/openapi.json` not found). New UI-15 (no logo in the Welcome hero) |

## debug-apk-1.9.4

`results/debug-apk-1.9.4/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.4_v1.0.pdf` | Retest of Talha's 1.9.4 list | 25 Nov, two phones (Ali and Ammi): **7 verified, 1 partly fixed, 9 still open, 1 new.** Verified: login, icon and name, native splash, consent line with Privacy and Terms, skeleton screens, F-17, the missed-medicine flow. Open: UI-15, F-13, F-29, F-24, F-28, F-18, F-27, N-13, N-16. New N-17 (notices pile up). Process note R-02: tags do not always match the built APK. Security items are in `results/security/debug-apk-1.9.4/` |

## debug-apk-1.9.5

`results/debug-apk-1.9.5/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.5_v1.0.pdf` | Retest of Talha's 1.9.5 list | 26 Nov, two phones: **12 verified, 4 partly fixed, 3 open, 4 new Low.** Verified: UI-01, UI-15, F-27, N-13, N-16, Privacy wording, consent line, skeleton screens, wrong-password message, back button, medicine flow, F-17. Partly fixed: UI-14, F-28, F-13, F-24. Open: F-29 (a call cannot be answered), N-17, F-18. New: UI-16, N-18, N-19, N-20. Security items are in `results/security/debug-apk-1.9.5/` |
| `Humsafar_QA_Design_vs_App_debug-apk-1.9.5_v1.1.pdf` | Design vs app | 26 Nov: second pass, 9 sets of screens not compared on 1.9.1 (splash, launch, Welcome, Dependent Home, Help is coming, medicine confirm, alarm, Guardian Home and Alerts, calling, Care schedules, Create account, Privacy). The Dependent's safety screens are close to the design. **New: UI-17, UI-18 (Medium), UI-19 to UI-22 (Low).** Screens still to compare are listed in the report |

## debug-apk-1.9.6

`results/debug-apk-1.9.6/`

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Retest_debug-apk-1.9.6_v1.0.pdf` | Retest of Talha's 1.9.6 list | 28 Nov, two phones (Ali Android 13, Ammi Android 9): **6 verified, 5 partly fixed, 5 still open, 4 new.** Verified: F-18 (with Abdullah's server change), F-28, UI-17, UI-18, UI-22, SEC-20 quick check (login, Panic, records PDF). Partly fixed: N-17, UI-14, UI-20, UI-21, N-20. Open: F-13, F-24, F-29 (no ringing or answer screen on Ammi's phone), N-18, N-19. New: N-21, N-22 (Dependent's notifications cannot be cleared), P-09, P-10. Decision UI-16: remove the tagline line on Welcome. Band, Urdu and release-only security items not tested |

**Versions:** v1.0 = matched to merged contracts and ready to run. v0.x = draft written ahead of time; it is updated when the matching backend contract lands, and the old version is removed from this folder.

Working Word files are kept in Google Drive (`Humsafar/02_QA`); only PDFs are added here.
