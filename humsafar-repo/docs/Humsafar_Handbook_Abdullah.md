# Humsafar — Individual Handbook: Muhammad Abdullah Ghafoor
### Role: Team Lead / Backend, Database, API, BLE Integration, System Architecture

**Source of truth:** This handbook is extracted directly from the Master Development Roadmap v1.0. Task numbers match the Master Roadmap exactly — nothing here has been re-planned or altered. If this handbook and the Master Roadmap ever appear to disagree, the Master Roadmap wins; flag the mismatch for correction.

**When you're blocked:** Every task below names who to contact. If a task has no listed contact, it means you can proceed independently — don't wait on anyone.

---

## Phase 0 — Environment Setup

#### 0.1 Create GitHub repo, branching strategy, .gitignore, README
- **Objective:** Establish the shared foundation everyone else builds on.
- **Deliverable:** Public/private repo with main/dev/feature branch structure, README with setup instructions.
- **Depends On:** Nothing — this is the true starting point of the project.
- **If Blocked, Contact:** N/A.
- **Feeds Into:** ICP-0.
- **Expected Output Before Moving On:** Talha and Sarim can both clone the repo and see the branch structure.

#### 0.2 FastAPI project skeleton
- **Objective:** Stand up the backend's basic structure before real endpoints exist.
- **Deliverable:** Running FastAPI app with a health-check endpoint, folder structure for routers/models/services.
- **Depends On:** 0.1.
- **If Blocked, Contact:** N/A.
- **Expected Output Before Moving On:** `GET /health` returns 200 locally.

#### 0.3 Local PostgreSQL + SQLAlchemy connection config
- **Objective:** Get a working database connection before schema work starts.
- **Deliverable:** Local Postgres instance, SQLAlchemy engine/session config committed to repo.
- **Depends On:** 0.1.
- **If Blocked, Contact:** N/A.
- **Expected Output Before Moving On:** A test script can connect and run a trivial query.

#### 0.5 Postman workspace + base collection structure
- **Objective:** Set up the shared API-testing environment early so it grows with every endpoint you build.
- **Deliverable:** Postman workspace shared with the team, folder structure matching your backend modules.
- **Depends On:** 0.2.
- **Expected Output Before Moving On:** Health-check endpoint callable from Postman.

**ICP-0 (Your Role):** Present repo + backend skeleton for review alongside Talha's Flutter skeleton and Sarim's wireframes.

---

## Phase 1 — Database & Core Identity Backend
*This phase is the critical path — Talha's Phase 1 integration work (task 1.11 onward) waits on you finishing 1.3-1.6.*

#### 1.1 SQLAlchemy models for all 27 tables (SDS 9.2)
- **Objective:** Translate the locked SDS schema into working models.
- **Deliverable:** Full model file(s) covering every table in SDS Section 9.2.
- **Depends On:** 0.3.
- **Expected Output Before Moving On:** Models import without error; match SDS table/column names exactly for traceability.

#### 1.2 Alembic migrations
- **Objective:** Version-control your schema so it can evolve safely.
- **Deliverable:** Initial migration creating all tables.
- **Depends On:** 1.1.
- **Expected Output Before Moving On:** `alembic upgrade head` runs clean on a fresh database.

#### 1.3 Auth endpoints: register, login, JWT issue/refresh
- **Objective:** Establish the authentication foundation almost everything else depends on.
- **Deliverable:** `POST /auth/register`, `POST /auth/login` returning valid JWT access + refresh tokens.
- **Depends On:** 1.2.
- **Expected Output Before Moving On:** Postman confirms token issuance and refresh working.

#### 1.4 Guardian/Dependent KYC endpoints (mocked verification provider)
- **Objective:** Fulfill FR-A2/FR-A3 without waiting on a real KYC vendor integration.
- **Deliverable:** KYC submission endpoint returning a mocked verified/pending/failed status.
- **Depends On:** 1.3.
- **Expected Output Before Moving On:** A registered account can be moved to "verified" state via the mocked flow.

#### 1.5 Guardian-Dependent linkage + cap enforcement (FR-B1, B2, B4)
- **Objective:** Implement the relationship model at the center of the whole system.
- **Deliverable:** Linkage endpoint enforcing exactly 1 Primary + up to 2 Secondary per Dependent; supports one Guardian linked to multiple Dependents.
- **Depends On:** 1.3.
- **Expected Output Before Moving On:** Attempting a 4th Guardian or 2nd Primary is correctly rejected.

#### 1.6 Permission dashboard endpoints (FR-A4)
- **Objective:** Build the access-control gate almost every later module checks against.
- **Deliverable:** Grant/revoke endpoints per module, per Secondary Guardian.
- **Depends On:** 1.5.
- **Expected Output Before Moving On:** Revoking a module immediately blocks that Secondary Guardian's access on the next API call.

#### 1.7 Postman collection for 1.3-1.6
- **Objective:** Keep the shared API reference current as you build.
- **Deliverable:** Documented requests/examples for every endpoint built so far.
- **Depends On:** 1.3-1.6 (update incrementally).
- **Expected Output Before Moving On:** Talha can use your Postman examples without asking you how to call an endpoint.

**ICP-1 (Your Role):** Confirm your Auth/Linkage/Permission APIs are stable before Talha wires the UI to them. Demo register → KYC → link → configure permissions live with Talha and Sarim.

---

## Phase 2 — Location, Geofencing, Device Health + BLE Spike

#### 2.1 Location ingestion + adaptive-frequency logic (FR-C1)
- **Depends On:** 1.6. **Expected Output:** Location updates stored, frequency adjusts with movement state.

#### 2.2 Geofence CRUD + breach detection (FR-C2, C3)
- **Depends On:** 2.1. **Expected Output:** Breach alert fires correctly for single- and multi-zone configurations.

#### 2.3 Battery/connectivity monitoring endpoints (FR-L1, L2)
- **Depends On:** 1.6. **Expected Output:** Low-battery and connectivity-loss alerts trigger at configured thresholds.

#### 2.4 BLE integration spike (critical de-risking task)
- **Objective:** Prove your BLE library and background-reconnection approach works **before** the wearable purchase is finalized, so the still-open market decision never blocks development.
- **Deliverable:** A working prototype using `flutter_blue_plus` or `flutter_reactive_ble` reading Heart Rate/Battery GATT characteristics from *any* available BLE HR device, with background reconnect tested.
- **Depends On:** Nothing — deliberately independent of the wearable purchase.
- **Expected Output Before Moving On:** You can confidently name which BLE library the team will use, backed by a working test, not a guess.

**ICP-2 (Your Role):** Present the BLE spike results — this locks in your BLE approach ahead of the actual device purchase.

---

## Phase 3 — The Core Safety Loop (Largest Phase — Build Order Matters Here)

#### 3.1 Notification service: priority tiers + acknowledgment tracking (FR-M1, M2)
- **Objective:** Build this **first** in the phase — Medication, Wellness Check, and Panic Mode all depend on it. Building it last would mean reworking all three.
- **Depends On:** 1.6. **Expected Output:** Critical-tier notifications distinguishable from standard; acknowledgment state recorded per notification.

#### 3.2 Medication scheduling + dual confirmation (FR-F1)
- **Depends On:** 3.1. **Expected Output:** Schedule created, reminder fires, dual-confirmation required to mark taken.

#### 3.3 Missed-dose escalation (FR-D1)
- **Depends On:** 3.1, 3.2. **Expected Output:** Unconfirmed dose past window triggers a Guardian alert automatically.

#### 3.4 Guardian Wellness Check scheduling + response (FR-D4)
- **Depends On:** 3.1. **Expected Output:** Configurable check windows, grace period, activity cross-check before escalating.

#### 3.5 Multi-level Escalation Engine (FR-D5)
- **Depends On:** 3.3, 3.4. **Expected Output:** Timeout-driven escalation from Primary → Secondary Guardian works correctly.

#### 3.6 Panic Mode endpoint (FR-D2)
- **Objective:** Implement the one deliberate exception in your permission model — this notifies all Guardians regardless of individual grants.
- **Depends On:** 3.1. **Expected Output:** Trigger notifies every linked Guardian, no permission check blocks it.

#### 3.7 Remote Alarm Override, Primary-only (FR-D3)
- **Depends On:** 1.6. **Expected Output:** Secondary Guardians are correctly rejected if they attempt this call.

#### 3.8 External Emergency Contact Fallback, mock SMS gateway (FR-R1)
- **Depends On:** 3.5. **Expected Output:** Escalation chain exhausting all Guardians correctly falls through to the mocked external contact notification.

**ICP-3 (Your Role) — the most important checkpoint in the project:** Backend must support triggering Panic Mode, simulating a missed Wellness Check through to external contact, and confirming a medication dose — all in one live sequence with Talha's UI and Sarim's test cases.

---

## Phase 4 — Communication & Notifications Completion

#### 4.1 Technical decision: RTC approach for voice/video (joint with Talha)
- **Objective:** Resolve the one remaining "what tool do we use" gap left open since the SDS.
- **Depends On:** Nothing — resolve at the start of this phase.
- **If Blocked, Contact:** Talha — this is a joint decision, not yours alone.
- **Expected Output Before Moving On:** A named, agreed RTC approach, not a placeholder.

#### 4.2 Text messaging endpoints (FR-E1)
- **Depends On:** 1.6. **Expected Output:** Messages persist and retrieve correctly between linked Guardian/Dependent.

#### 4.3 Priority voice message endpoints (FR-E4)
- **Depends On:** 3.1. **Expected Output:** Voice messages flagged high-priority route through the notification tier correctly.

#### 4.4 Voice/video call signaling endpoints (FR-E2)
- **Depends On:** 4.1. **Expected Output:** Call session establishes correctly using the chosen RTC approach.

#### 4.5 Multi-guardian bridge call logic (FR-E5, Optional)
- **Depends On:** 4.4. **Expected Output:** All linked Guardians can be joined into one call during an active emergency.

**ICP-4 (Your Role):** Confirm messaging and calling endpoints are stable for Talha's UI integration.

---

## Phase 5 — Medical Records, Vitals & Wearable Integration

#### 5.1 Medical vault CRUD + PDF export + appointments (FR-G1, G3, G4)
- **Depends On:** 1.6. **Expected Output:** Records stored, exportable as complete/year/month PDFs, appointments scheduled with reminders.

#### 5.2 Field-level access control on records (FR-G2)
- **Depends On:** 5.1. **Expected Output:** Secondary Guardian record-category restrictions enforced correctly.

#### 5.3 Manual vitals entry endpoints (FR-H1)
- **Depends On:** 1.6. **Expected Output:** Vitals entries stored, attributable to either Dependent or Guardian.

#### 5.4 Wearable sync endpoint (FR-H2) — build against mocked data first
- **Objective:** Don't let the still-open wearable purchase block this task.
- **Depends On:** 3.1. **Expected Output:** Endpoint accepts and stores mocked heart-rate/battery payloads correctly.

#### 5.5 Real wearable integration, once purchased
- **Objective:** Swap mocked data for the actual chosen device, using the BLE approach proven in 2.4.
- **Depends On:** 5.4, 2.4, and the team's wearable purchase (external, not on you to control the timing of).
- **If Blocked, Contact:** Whoever is tracking the market-comparison purchase — confirm the exact model and its confirmed GATT services before starting.
- **Expected Output Before Moving On:** Live heart-rate data flows from the real device through to the backend.

**ICP-5 (Your Role):** Demo records/vitals; demo live wearable data if purchased by this point, mocked data if not — either is acceptable here.

---

## Phase 6 — Directory, Marketplace, Camera & Security Hardening

#### 6.1 Healthcare directory + provider directory endpoints, seed data (FR-I1, J1)
- **Depends On:** 1.6. **Expected Output:** Directory listings retrievable and searchable.

#### 6.2 Booking requests + shared activity log (FR-I2/J2)
- **Depends On:** 6.1. **Expected Output:** Single unified activity log serving both healthcare contacts and marketplace bookings.

#### 6.3 Camera stream service + permission gating (FR-K1)
- **Depends On:** 1.6. **Expected Output:** Stream access correctly gated by permission dashboard.

#### 6.4 Event-triggered clip capture (FR-K2)
- **Depends On:** 6.3, 3.6, 3.7. **Expected Output:** Clip auto-captured on Panic Mode or Remote Alarm trigger.

#### 6.5 Encryption in transit/at rest, formalize (FR-N1, N2)
- **Depends On:** Ongoing — formalize and verify now. **Expected Output:** TLS confirmed everywhere; records/vitals/location confirmed encrypted at rest.

#### 6.6 Audit logging (FR-N3)
- **Depends On:** 1.6, 6.3. **Expected Output:** Permission changes, camera views, and record access all logged with actor/action/timestamp.

#### 6.7 Data retention job (FR-O1)
- **Depends On:** 6.6. **Expected Output:** Scheduled job correctly deletes/anonymizes data per the retention policy.

#### 6.10 Set up spare phone in camera mode (joint with Talha)
- **Objective:** Implement the locked hardware decision — no dedicated camera purchase.
- **If Blocked, Contact:** Talha — this is joint frontend/backend work.
- **Expected Output Before Moving On:** Spare phone streams reliably to the Guardian app over the local network.

**ICP-6 (Your Role):** Confirm camera stream + clip capture work end-to-end via the spare phone; directory/booking backend stable.

---

## Phase 7 — Analytics, Accessibility Polish, Localization Completion

#### 7.1 Analytics aggregation endpoints (FR-Q1)
- **Depends On:** 3.2, 5.3, 5.4. **Expected Output:** Adherence and vitals trends computed correctly.

#### 7.2 Summary report generation (FR-Q2)
- **Depends On:** 7.1, 5.1. **Expected Output:** Scheduled summary reports generated combining trends with PDF export.

**ICP-7 (Your Role):** Confirm analytics endpoints support Talha's dashboard build.

---

## Phase 8 — System Integration Testing & NFR Validation

#### 8.2 Performance testing: NFR-01, NFR-02, NFR-06
- **Depends On:** 8.1 (Sarim's use-case test pass). **Expected Output:** Latency, battery, and concurrency targets measured and documented.

#### 8.3 BLE reliability testing: NFR-13
- **Depends On:** 5.5 (real device integrated). **Expected Output:** Reconnection within 30 seconds confirmed on the real device.

#### 8.4 Bug-fixing sprint
- **Depends On:** 8.1-8.3. **Contact:** All — this is a shared task, triage together.

#### 8.5 Security review finalization
- **Depends On:** 6.13 (Sarim's security review pass). **Expected Output:** All flagged security items closed.

**ICP-8 (Your Role):** Backend stability confirmed for full demo dry-run.

---

## Phase 9 — Deployment

#### 9.1 Provision Render (or equivalent) backend + PostgreSQL
- **Depends On:** 8.4. **Expected Output:** Production environment provisioned.

#### 9.2 Environment configs, secrets management
- **Depends On:** 9.1. **Expected Output:** No secrets committed to the repo; environment variables documented.

#### 9.3 Deploy backend; run full Postman collection against production
- **Depends On:** 9.2. **Expected Output:** Every endpoint verified working in production, not just locally.

#### 9.5 Smoke test production environment
- **Depends On:** 9.3, Talha's 9.4 (release APK built).
- **Contact:** All — shared final check.
- **Expected Output Before Moving On:** Backend confirmed stable under the actual release build, not just Postman.

**ICP-9 (Your Role):** Confirm production deployment before Talha builds the release APK against it.

---

## Phase 10 — Documentation & Demo Preparation

#### 10.3 Demo script — joint with Sarim
- **Objective:** Plan feature order, timing, and a fallback plan if hardware misbehaves live.
- **If Blocked, Contact:** Sarim.

#### 10.4 / 10.5 Full rehearsal + final bug-fix buffer
- **Contact:** All — shared responsibility.

**ICP-10 (Final, Your Role):** Backend fully stable and demoed live.

---

## Quick Reference: Who to Contact

| If you're blocked on... | Contact |
|---|---|
| UI not reflecting your API changes | Talha |
| Design/wireframe ambiguity | Sarim |
| Wearable purchase status/specs | Whoever is tracking the market visit |
| RTC SDK decision | Talha (joint decision, Task 4.1) |
| Demo script / presentation | Sarim (Task 10.3) |
