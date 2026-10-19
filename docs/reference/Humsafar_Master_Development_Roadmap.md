# Humsafar — Master Development Roadmap

**Status:** Official execution plan, Version 1.0
**Basis:** Locked SRS v1.0, SDS v1.0, Hardware Selection & Integration Document, and the locked technology stack (Flutter, FastAPI, PostgreSQL, SQLAlchemy, JWT, Postman, Git/GitHub, Render)
**Team:** Muhammad Abdullah (Team Lead — Backend/DB/API/BLE/Integration/Architecture), Muhammad Talha Khan (Flutter/API Integration/State Management/FCM), Syed Sarim Jawad (UI/UX/Documentation/Diagrams/Testing/Presentation)

This document sequences the entire project from current state to final demonstration. Individual member roadmaps (Humsafar — Abdullah / Talha / Sarim) will be generated after this is reviewed and approved, and will be extracted directly from the task assignments below — nothing new will be introduced at that stage.

---

## How to Read This Roadmap

- Tasks are numbered **Phase.Task** (e.g., 3.4). Each task lists **Owner**, **Depends On**, and whether it runs on a **Parallel Track**.
- Three parallel tracks run through most phases: **Backend Track** (Abdullah), **Frontend Track** (Talha), **Design/QA/Docs Track** (Sarim). Where a track has no dependency on that phase's backend work, it starts immediately rather than waiting.
- **Integration Checkpoints (ICP)** mark the end of each phase, where all three members' work merges into one working, demonstrable slice of the system before moving on.
- Sprint lengths are estimates (roughly 1-2 weeks each) — adjust to your actual semester calendar; the sequencing and dependencies matter more than the exact durations.

---

## Critical Path (What Actually Determines Project Duration)

Repo/environment setup → Database schema → Auth/Identity endpoints → Permission dashboard → **everything else branches out from here in parallel**. This is the only place in the project where Talha and Sarim have to wait on Abdullah before their own tracks can *integrate* (not before they can *start* — see Phase 0-1 below, where both have independent work ready from day one).

The second real dependency point is the **BLE spike (Task 2.4)**, deliberately scheduled early and decoupled from the wearable purchase, so the still-open wearable decision never blocks development.

---

## Phase 0 — Project Kickoff & Environment Setup
*Sprint 0 (~3-5 days). Goal: everyone has a working local environment and a shared design foundation.*

| # | Task | Owner | Depends On | Track |
|---|---|---|---|---|
| 0.1 | Create GitHub repo, branching strategy (main/dev/feature), .gitignore, README | Abdullah | — | Backend (blocking — do first) |
| 0.2 | FastAPI project skeleton (folder structure, virtualenv, requirements.txt, health-check endpoint) | Abdullah | 0.1 | Backend |
| 0.3 | Local PostgreSQL instance + SQLAlchemy connection config | Abdullah | 0.1 | Backend |
| 0.4 | Flutter project skeleton (folder structure, Riverpod setup, routing skeleton) | Talha | 0.1 | Frontend — parallel with 0.2/0.3 |
| 0.5 | Postman workspace + base collection structure | Abdullah | 0.2 | Backend |
| 0.6 | Set up shared documentation/design workspace (Figma or equivalent) | Sarim | — | Design — parallel with everything |
| 0.7 | Low-fidelity wireframes for all screens (SDS Section 10.1 screen list) | Sarim | 0.6 | Design — parallel with 0.2-0.5 |

**ICP-0:** Repo, backend skeleton, Flutter skeleton, and the full wireframe set reviewed together. No code integration yet — just confirming everyone is building from the same foundation.

---

## Phase 1 — Database & Core Identity Backend
*Sprint 1 (~1-2 weeks). Goal: registration, KYC, linkage, and permissions work end-to-end.*

**Backend Track (Abdullah) — the critical path:**

| # | Task | Depends On |
|---|---|---|
| 1.1 | SQLAlchemy models for all 27 tables (SDS 9.2) | 0.3 |
| 1.2 | Alembic migrations | 1.1 |
| 1.3 | Auth endpoints: register, login, JWT issue/refresh | 1.2 |
| 1.4 | Guardian/Dependent KYC endpoints (mocked verification provider) | 1.3 |
| 1.5 | Guardian-Dependent linkage + cap enforcement (FR-B1, B2, B4) | 1.3 |
| 1.6 | Permission dashboard endpoints (FR-A4) | 1.5 |
| 1.7 | Postman collection for 1.3-1.6, with example requests | 1.3-1.6 (incremental) |

**Frontend Track (Talha) — no backend dependency, starts immediately:**

| # | Task | Depends On |
|---|---|---|
| 1.8 | Navigation shell (Guardian app + Dependent app routing) | 0.4 |
| 1.9 | Theming system: standard + large-text/high-contrast toggle (FR-P2) | 0.4 |
| 1.10 | Localization scaffold (English/Urdu) | 0.4 |
| 1.11 | Static registration/login/KYC-capture screens (UI only) | 1.8, 0.7 (wireframes) |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 1.12 | High-fidelity mockups for Identity & Access screens | 0.7 |
| 1.13 | Draft project-wide test plan / QA checklist template | — |
| 1.14 | Begin architecture/workflow diagrams for the final presentation (reuse SDS diagrams as a base) | — |

**ICP-1:** Talha wires the registration/login UI to Abdullah's live Auth API. Full flow demoed by all three: register → KYC → link Dependent → Primary configures permissions. Sarim tests it against the QA checklist from 1.13.

---

## Phase 2 — Location, Geofencing, Device Health + Early BLE De-Risking
*Sprint 2 (~1-2 weeks). Goal: live location and geofencing work; BLE approach is validated before the wearable is even purchased.*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 2.1 | Location ingestion endpoint + adaptive-frequency logic (FR-C1) | 1.6 |
| 2.2 | Geofence CRUD + breach detection (FR-C2, C3) | 2.1 |
| 2.3 | Battery/connectivity monitoring endpoints (FR-L1, L2) | 1.6 |
| 2.4 | **BLE integration spike:** prototype `flutter_blue_plus`/`flutter_reactive_ble` background scan + reconnect using *any* available BLE HR device (borrowed, generic, doesn't need to be the final purchase) | — (deliberately independent of the wearable decision) |

**Frontend Track (Talha):**

| # | Task | Depends On |
|---|---|---|
| 2.5 | Integrate Identity/Linkage/Permission screens with real APIs | ICP-1 |
| 2.6 | Live Map screen (location + geofence overlay) | 2.1, 2.2, Sarim's mockup (2.8) |
| 2.7 | Background location service in Flutter (permissions, adaptive polling) | 2.1 |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 2.8 | High-fidelity mockups: Live Map, Geofence config, Dependent Mode home | 0.7 |
| 2.9 | QA pass on Phase 1 deliverables | ICP-1 |
| 2.10 | Continue architecture/workflow diagrams | — |

**ICP-2:** Live location + geofence breach alert demoed end-to-end. **The BLE spike (2.4) is reviewed here — this confirms your BLE library choice and de-risks NFR-13 before the market-comparison purchase is even finalized.**

---

## Phase 3 — The Core Safety Loop (Medication, Wellness Check, Panic Mode, Escalation)
*Sprints 3-4 (~2-3 weeks). This is the largest phase and the actual value proposition of the system — give it the most room.*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 3.1 | Notification service: priority tiers + acknowledgment tracking (FR-M1, M2) | 1.6 — **build this first**, everything else in this phase depends on it |
| 3.2 | Medication scheduling + dual confirmation (FR-F1) | 3.1 |
| 3.3 | Missed-dose escalation (FR-D1) | 3.1, 3.2 |
| 3.4 | Guardian Wellness Check scheduling + response (FR-D4) | 3.1 |
| 3.5 | Multi-level Escalation Engine (FR-D5) | 3.3, 3.4 |
| 3.6 | Panic Mode endpoint, bypasses permission gating (FR-D2) | 3.1 |
| 3.7 | Remote Alarm Override, Primary-only (FR-D3) | 1.6 |
| 3.8 | External Emergency Contact Fallback, mock SMS gateway (FR-R1) | 3.5 |

**Design/QA/Docs Track (Sarim) — front-load this so Talha isn't waiting:**

| # | Task | Depends On |
|---|---|---|
| 3.9 | High-fidelity mockups for all Dependent Mode screens + Guardian alert/config screens | 0.7 — **do this at the very start of the phase** |

**Frontend Track (Talha) — starts once 3.9 mockups exist, integrates as backend endpoints land:**

| # | Task | Depends On |
|---|---|---|
| 3.10 | Dependent Mode home screen (1-tap access to the 3 safety actions) | 1.9, 3.9 |
| 3.11 | Panic Mode screen | 3.6, 3.10 |
| 3.12 | Wellness Check response screen | 3.4, 3.10 |
| 3.13 | Medication Confirmation screen (dual-step) | 3.2, 3.10 |
| 3.14 | Guardian-side alert/notification UI + FCM integration | 3.1 |
| 3.15 | Guardian-side schedule configuration screens | 3.2, 3.4 |

**Design/QA/Docs Track (Sarim) — continued through the phase:**

| # | Task | Depends On |
|---|---|---|
| 3.16 | Accessibility audit: 2-tap rule (NFR-07), contrast ratios (NFR-08) on Dependent Mode | 3.11-3.13 |
| 3.17 | QA test cases for the full escalation chain, including simulated missed check → escalation → external contact | 3.5, 3.8 |
| 3.18 | Documentation/diagram updates reflecting Phase 3 | ongoing |

**ICP-3 — the most important checkpoint in the project:** trigger Panic Mode, simulate a missed Wellness Check all the way through to the External Emergency Contact notification, confirm a medication dose — all visible live on the Guardian dashboard. If this checkpoint works cleanly, the hardest part of Humsafar is done.

---

## Phase 4 — Communication & Notifications Completion
*Sprint 5 (~1-2 weeks)*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 4.1 | **Technical decision (joint with Talha):** select the RTC approach for voice/video — e.g., `flutter_webrtc` vs. a hosted SDK. Not yet decided anywhere in your documentation — resolve this at the start of this phase, not mid-build. | — |
| 4.2 | Text messaging endpoints (FR-E1) | 1.6 |
| 4.3 | Priority voice message endpoints (FR-E4) | 3.1 |
| 4.4 | Voice/video call signaling endpoints (FR-E2) | 4.1 |
| 4.5 | Multi-guardian bridge call logic (FR-E5, Optional) | 4.4 |

**Frontend Track (Talha):**

| # | Task | Depends On |
|---|---|---|
| 4.6 | Messaging UI (chat thread) | 4.2 |
| 4.7 | Voice/video call UI + RTC integration | 4.1, 4.4 |
| 4.8 | Priority voice message recorder UI | 4.3 |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 4.9 | Mockups for communication screens | early in phase |
| 4.10 | QA: messaging + calling flows | 4.6-4.8 |

**ICP-4:** Guardian-Dependent messaging and calling demoed end-to-end.

---

## Phase 5 — Medical Records, Vitals & Wearable Integration
*Sprint 6 (~1-2 weeks). Designed so the still-open wearable purchase never blocks this phase.*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 5.1 | Medical vault CRUD + PDF export + appointments (FR-G1, G3, G4) | 1.6 |
| 5.2 | Field-level access control on records (FR-G2) | 5.1 |
| 5.3 | Manual vitals entry endpoints (FR-H1) | 1.6 |
| 5.4 | Wearable sync endpoint (FR-H2) — **build and test against mocked BLE data first; do not wait on the purchase** | 3.1 |
| 5.5 | Once the wearable is purchased: integrate the specific device using the BLE library validated in the Phase 2 spike | 5.4, 2.4, wearable purchase (external, team-driven) |

**Frontend Track (Talha):**

| # | Task | Depends On |
|---|---|---|
| 5.6 | Medical records UI (list, upload, export) | 5.1 |
| 5.7 | Vitals entry UI | 5.3 |
| 5.8 | Wearable pairing UI (Dependent side) | 5.4, real device once 5.5 lands |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 5.9 | Mockups for records/vitals/wearable screens | early in phase |
| 5.10 | QA: records/export/vitals flows | 5.6-5.7 |
| 5.11 | Update the Hardware Selection & Integration Document with the final wearable's exact specs once purchased (coordinate with Abdullah) | wearable purchase |

**ICP-5:** Records + vitals demoed; live wearable heart-rate feed demoed if the device has been purchased by this point (if not, demoed against mocked data — not a blocker).

---

## Phase 6 — Directory, Marketplace, Camera & Security Hardening
*Sprint 7 (~1-2 weeks)*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 6.1 | Healthcare directory + provider directory endpoints, seed data (FR-I1, J1) | 1.6 |
| 6.2 | Booking requests + shared activity log (FR-I2/J2) | 6.1 |
| 6.3 | Camera stream service + permission gating (FR-K1) | 1.6 |
| 6.4 | Event-triggered clip capture (FR-K2) | 6.3, 3.6, 3.7 |
| 6.5 | Encryption in transit/at rest audit, formalize (FR-N1, N2) | ongoing, formalize now |
| 6.6 | Audit logging (FR-N3) | 1.6, 6.3 |
| 6.7 | Data retention job (FR-O1) | 6.6 |

**Frontend Track (Talha):**

| # | Task | Depends On |
|---|---|---|
| 6.8 | Directory/marketplace UI | 6.1, 6.2 |
| 6.9 | Camera view UI, live stream + on-screen viewing indicator (FR-K1.3) | 6.3 |
| 6.10 | Set up the spare phone in camera mode — per the Hardware Document's Flutter-native suggestion, this can be your own app's "camera mode" rather than a third-party app | joint with Abdullah |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 6.11 | Mockups for directory/camera screens | early in phase |
| 6.12 | QA: camera + directory flows; verify the privacy indicator actually appears | 6.9 |
| 6.13 | Security review pass (checklist-based, paired with Abdullah) | 6.5, 6.6 |

**ICP-6:** Camera live view and clip capture demoed via the spare phone; directory/booking flow demoed.

---

## Phase 7 — Analytics, Accessibility Polish, Localization Completion
*Sprint 8 (~1 week)*

**Backend Track (Abdullah):**

| # | Task | Depends On |
|---|---|---|
| 7.1 | Analytics aggregation endpoints (FR-Q1) | 3.2, 5.3, 5.4 |
| 7.2 | Summary report generation (FR-Q2) | 7.1, 5.1 |

**Frontend Track (Talha):**

| # | Task | Depends On |
|---|---|---|
| 7.3 | Analytics dashboard UI (charts) | 7.1 |
| 7.4 | Complete Urdu localization across every screen (FR-P4) | all prior UI tasks |
| 7.5 | Final accessibility pass: NFR-07 (2-tap), NFR-08 (contrast) | 3.16, reviewed by Sarim |

**Design/QA/Docs Track (Sarim):**

| # | Task | Depends On |
|---|---|---|
| 7.6 | Full documentation refresh — confirm SRS/SDS/Reference Guide/Hardware doc still match what was actually built; flag any drift | all phases |
| 7.7 | QA regression pass across all modules | all phases |

**ICP-7:** Analytics dashboard demoed; full localization and accessibility verified against the NFRs.

---

## Phase 8 — System Integration Testing & NFR Validation
*Sprint 9 (~1-2 weeks)*

| # | Task | Owner | Depends On |
|---|---|---|---|
| 8.1 | End-to-end test pass across all 22 use cases | Sarim leads, Abdullah + Talha support | ICP-7 |
| 8.2 | Performance testing: NFR-01 (2s latency), NFR-02 (battery), NFR-06 (3 concurrent Guardians) | Abdullah | 8.1 |
| 8.3 | BLE reliability testing: NFR-13 reconnection, on the real purchased device | Abdullah | 5.5 |
| 8.4 | Bug-fixing sprint, triaged by severity | All | 8.1-8.3 |
| 8.5 | Security review finalization | Abdullah | 6.13 |

**ICP-8:** Full system demo dry-run #1.

---

## Phase 9 — Deployment
*Sprint 10 (~3-5 days)*

| # | Task | Owner | Depends On |
|---|---|---|---|
| 9.1 | Provision Render (or equivalent) backend + PostgreSQL | Abdullah | 8.4 |
| 9.2 | Environment configs, secrets management | Abdullah | 9.1 |
| 9.3 | Deploy backend; run the full Postman collection against production | Abdullah | 9.2 |
| 9.4 | Build release APK, install on demo devices | Talha | 9.3 |
| 9.5 | Smoke test the production environment | All | 9.4 |

**ICP-9:** Production deployment verified end-to-end.

---

## Phase 10 — Documentation & Demo Preparation
*Sprint 11 (~1 week)*

| # | Task | Owner | Depends On |
|---|---|---|---|
| 10.1 | Final consistency check across all project documents | Sarim | 9.5 |
| 10.2 | Presentation slides | Sarim | 10.1 |
| 10.3 | Demo script — feature order, timing, fallback plan if hardware misbehaves live | Sarim + Abdullah | 9.5 |
| 10.4 | Full demo rehearsal | All | 10.3 |
| 10.5 | Final bug-fix buffer | All | 10.4 |

**ICP-10 (Final):** FYP demonstration ready.

---

## Bottleneck-Prevention Design Notes

- **Sarim's mockups always run one step ahead of Talha's builds** (0.7 before 1.11, 3.9 before 3.10-3.15, etc.) so Talha is never blocked waiting on design.
- **The BLE spike (2.4) is deliberately decoupled from the wearable purchase.** Your team hasn't chosen a final device yet — this roadmap doesn't wait for that decision. By the time you do purchase, the integration pattern is already proven.
- **Notification Service (3.1) is sequenced before Medication/Escalation/Panic Mode**, not after, because all three depend on it — building it last would have forced rework.
- **The RTC SDK decision (4.1)** is flagged as an explicit joint decision task rather than left implicit, since it's the one remaining "what tool do we actually use" gap in your documentation.
- **No phase past Phase 1 has a task that blocks all three members simultaneously** — there is always an independent design, QA, or documentation task available.

---

## Next Step

Once this Master Roadmap is reviewed and approved by the team, request the three individual roadmaps:
- **Humsafar — Abdullah**
- **Humsafar — Talha**
- **Humsafar — Sarim**

Each will extract that member's tasks directly from this document, in sequence, as their dedicated working guide.
