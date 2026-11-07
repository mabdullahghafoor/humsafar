# qa/ — Quality assurance

**Owner:** Sarim

**Contents**

| File | Task | Status |
|---|---|---|
| `Humsafar_QA_Checklist_Template_v1.0.pdf` | 1.13 | Reusable checklist |
| `Humsafar_QA_Phase1_Results_v1.0.pdf` | 2.9 | Phase 1 QA results (Postman run + functional / security checks) |
| `Humsafar_QA_Backend_Regression_Phases1-7_Results_v2.0.pdf` | 7.7 | QA regression pass of the whole backend, Phases 1–7 (Tasks 1.3–7.2): full Postman collection, 30 folders, 949 requests, 1501 / 1501 checks passed, 0 product bugs (22 Oct 2026, dev 7467459). Replaces v1.0 (Phases 1–6.1) |
| `Humsafar_QA_3.17_Escalation_Test_Cases_v1.0.pdf` | 3.17 | Escalation chain cases + ICP-3 live script |
| `Humsafar_QA_ICP3_Results_v1.1.pdf` | ICP-3 (3.17) | Run 1 split run (4 Nov) + Run 2 on two phones by Sarim (7 Nov, debug-apk-1.8, normal timers): 8 PASS, 2 partial, 1 FAIL (Remote Alarm never rings), 1 skipped. SMS to the emergency contact proven (5 min 39 s). **Not passed yet: F-16 Critical (backend) — the server sends no real push to any phone.** Also F-10, F-13 High; F-12, F-14, F-15 Medium; F-11, F-17, F-18 Low (frontend). Replaces v1.0 |
| `Humsafar_QA_Retest_debug-apk-1.8_v1.0.pdf` | ICP-1, 3.16, 6.12 | Retest of the open items on debug-apk-1.8 (30 Oct, 7 Nov): G-01, N-01, G-02, F-03, F-05, F-09 Verified; A-04, D-09–D-11, D-13, D-16, KYC resume, bottom sheets PASS; back swipe on the signed-in Home closes the app (F-19, Low); A-05 blocked by real push; D-12, D-14, D-17 not run. New Low findings F-19, N-15. Updates ICP-1 v1.1, 3.16 v1.0, 6.12 v1.0 |
| `Humsafar_QA_3.16_Accessibility_Test_Cases_v0.1.pdf` | 3.16 | Accessibility of Dependent Mode: 2 taps (NFR-07), large text and contrast (NFR-08), touch targets, Urdu; written ahead, run waits for Talha's 3.11–3.13 |
| `Humsafar_QA_3.16_Accessibility_Results_v1.0.pdf` | 3.16 | Accessibility audit on a real phone (debug-apk-1.7, 30 Oct): 20 / 27 PASS, 4 partial, 1 FAIL (large text not remembered), 2 blocked (medicine cannot be added, High). 14 findings (1 High, 6 Medium, 7 Low) for Talha's 7.5 |
| `Humsafar_QA_4.10_Messaging_Calls_Test_Cases_v1.0.pdf` | 4.10 | Messaging, urgent voice and calls cases + ICP-4 live script |
| `Humsafar_QA_5.10_Records_Vitals_Test_Cases_v0.4.pdf` | 5.10 | Records, record categories per Secondary, appointments, vitals and band (mock data) from the 5.1–5.4 contracts; two real-band cases wait for 5.5 |
| `Humsafar_QA_5.10_Records_Vitals_Results_v1.0.pdf` | 5.10 / ICP-5 | First pass on two phones (debug-apk-1.8, 7 Nov): 12 / 18 PASS, 2 partial, 4 FAIL. Saving works everywhere; High M-01 doctor link shared without the server address, High M-02 Analytics crashes once there are vitals; Medium M-03 records export fails in the app, F-20 stuck on KYC after an interrupted sign-up; Low M-05–M-08. Band, Secondary-permission and Postman cases in a second pass |
| `Humsafar_QA_6.12_Camera_Directory_Test_Cases_v0.4.pdf` | 6.12 | Camera live view and viewing notice (K-01–K-11) and emergency clips (K-12–K-17) from the 6.3 / 6.4 contract; directory (D-01–D-08) and requests / Activity Timeline (D-09–D-18) |
| `Humsafar_QA_6.12_Directory_Results_v1.0.pdf` | 6.12 | Directory half run on a real phone (debug-apk-1.7, 30 Oct): 8 / 18 PASS, 2 partial, 1 FAIL, 3 blocked, 4 not run. Critical G-01: the app's client_id is not a UUID, so visit requests, text / voice messages, new records and vitals readings all fail (fix in 1.8). Camera half waits for the camera phone (6.10) |
| `Humsafar_QA_6.13_Security_Review_v0.3.pdf` | 6.13 | Security review checklist from SDS 17 and the 6.5 security guide: 29 checks (14 pass by code review, 5 passed in Postman runs: 7.7 run 22 Oct + hand checks S-09 / S-12 on the hosted server 30 Oct, 4 still to run: S-04 device, S-16 4-viewer limit, S-15 / S-26 with Abdullah), 5 findings (1 High resolved: app privacy notice field names; 2 Medium: no end-to-end A/V, host disk encryption) |
| `Humsafar_QA_6.13_Hand_Checks.postman_collection.json` | 6.13 | Postman collection for the hand checks S-09 (wrong phone codes → 429) and S-12 (camera stream token not cached); makes its own random test accounts. Run with base_url set to the hosted server or a local backend |
| `Humsafar_QA_NFR-08_Contrast_Check_v1.0.pdf` | 3.16 (prep) | Colour contrast of the style guide, all hi-fi screens and the app's colours against WCAG AA; two token fixes |
| `Humsafar_QA_8.1_E2E_Test_Plan_v0.3.pdf` | 8.1 | End-to-end test plan draft (v0.3: all 22 use cases now have their backend, Tasks 6.2–7.2) |

**Versions:** v1.0 = matched to merged contracts and ready to run. v0.x = draft written ahead of time; it is updated when the matching backend contract lands, and the old version is removed from this folder.

Working Word files are kept in Google Drive (`Humsafar/02_QA`); only PDFs are added here.
