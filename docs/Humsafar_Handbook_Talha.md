# Humsafar — Individual Handbook: Muhammad Talha Khan
### Role: Flutter Frontend, API Integration, State Management, FCM

**Source of truth:** This handbook is extracted directly from the Master Development Roadmap v1.0. Task numbers match the Master Roadmap exactly. If this handbook and the Master Roadmap ever disagree, the Master Roadmap wins — flag the mismatch.

**When you're blocked:** Every task below names who to contact. If a task has no listed contact, it means you can proceed independently.

---

## Phase 0 — Environment Setup

#### 0.4 Flutter project skeleton
- **Objective:** Stand up your app structure — this doesn't wait on Abdullah's backend at all.
- **Deliverable:** Folder structure, Riverpod setup, routing skeleton.
- **Depends On:** 0.1 (repo must exist first).
- **If Blocked, Contact:** Abdullah, only if the repo itself isn't ready.
- **Expected Output Before Moving On:** App runs on an emulator/device showing empty navigation shell.

**ICP-0 (Your Role):** Present the Flutter skeleton alongside Abdullah's backend skeleton and Sarim's wireframes.

---

## Phase 1 — Identity & Access (Frontend Track — Starts Immediately, No Backend Wait)

#### 1.8 Navigation shell (Guardian app + Dependent app routing)
- **Depends On:** 0.4. **Expected Output:** Both app entry points navigable, even with placeholder screens.

#### 1.9 Theming system: standard + large-text/high-contrast toggle (FR-P2)
- **Depends On:** 0.4. **Expected Output:** Theme toggle works and visibly changes text size/contrast.

#### 1.10 Localization scaffold (English/Urdu)
- **Depends On:** 0.4. **Expected Output:** String resource structure in place for both languages, even if Urdu strings are placeholders for now.

#### 1.11 Static registration/login/KYC-capture screens (UI only)
- **Objective:** Build the UI shell before Abdullah's Auth API is ready, so you're not idle.
- **Depends On:** 1.8, and Sarim's wireframes (Task 0.7).
- **If Blocked, Contact:** Sarim, if wireframes aren't ready yet.
- **Expected Output Before Moving On:** Screens navigable with dummy data, ready to wire to real endpoints.

**ICP-1 (Your Role):** Wire your registration/login UI to Abdullah's live Auth API. Demo the full register → KYC → link → permissions flow with Abdullah and Sarim.

---

## Phase 2 — Location, Geofencing, Device Health

#### 2.5 Integrate Identity/Linkage/Permission screens with real APIs
- **Depends On:** ICP-1. **Expected Output:** No more dummy data — everything hits Abdullah's real endpoints.

#### 2.6 Live Map screen (location + geofence overlay)
- **Depends On:** Abdullah's 2.1/2.2, Sarim's mockup (2.8).
- **If Blocked, Contact:** Abdullah (API not ready) or Sarim (mockup not ready).
- **Expected Output Before Moving On:** Live location and geofence boundary both render correctly on the map.

#### 2.7 Background location service in Flutter
- **Objective:** Handle permissions and adaptive polling on the client side.
- **Depends On:** Abdullah's 2.1.
- **Expected Output Before Moving On:** Location updates continue reliably with the app backgrounded.

**ICP-2 (Your Role):** Demo live location + geofence breach alert end-to-end. (BLE spike review is Abdullah's part of this checkpoint — you're not blocked by it.)

---

## Phase 3 — The Core Safety Loop (Wait for Sarim's Mockups First, Then Build in Order)

#### 3.10 Dependent Mode home screen (1-tap access to the 3 safety actions)
- **Depends On:** 1.9 (theming), Sarim's Task 3.9 (mockups — done at the start of this phase specifically so you're not waiting).
- **If Blocked, Contact:** Sarim, if mockups for Dependent Mode aren't ready yet.
- **Expected Output Before Moving On:** Home screen reachable in Dependent Mode with clear paths to all three safety actions.

#### 3.11 Panic Mode screen
- **Depends On:** Abdullah's 3.6, your 3.10.
- **If Blocked, Contact:** Abdullah, if the Panic Mode endpoint isn't ready.
- **Expected Output Before Moving On:** Tapping Panic Mode triggers the real backend call and confirms delivery.

#### 3.12 Wellness Check response screen
- **Depends On:** Abdullah's 3.4, your 3.10.
- **Expected Output Before Moving On:** Scheduled prompts appear and responses are correctly recorded.

#### 3.13 Medication Confirmation screen (dual-step)
- **Depends On:** Abdullah's 3.2, your 3.10.
- **Expected Output Before Moving On:** Dual confirmation correctly prevents single-tap accidental marking.

#### 3.14 Guardian-side alert/notification UI + FCM integration
- **Objective:** This is squarely your strength — own it fully.
- **Depends On:** Abdullah's 3.1 (Notification Service).
- **Expected Output Before Moving On:** Critical alerts arrive as push notifications, visually distinct from standard ones.

#### 3.15 Guardian-side schedule configuration screens
- **Depends On:** Abdullah's 3.2, 3.4.
- **Expected Output Before Moving On:** Guardian can configure medication schedules and Wellness Check windows from the app.

**ICP-3 (Your Role) — the most important checkpoint in the project:** Your UI must support triggering Panic Mode, responding to a Wellness Check, and confirming medication — all live, feeding into Abdullah's escalation chain and Sarim's test cases.

---

## Phase 4 — Communication & Notifications Completion

#### 4.1 Technical decision: RTC approach for voice/video (joint with Abdullah)
- **If Blocked, Contact:** Abdullah — this is a joint decision, resolve it before building call UI.

#### 4.6 Messaging UI (chat thread)
- **Depends On:** Abdullah's 4.2. **Expected Output:** Messages send/receive correctly in real time.

#### 4.7 Voice/video call UI + RTC integration
- **Depends On:** 4.1, Abdullah's 4.4. **Expected Output:** Calls connect reliably using the chosen RTC approach.

#### 4.8 Priority voice message recorder UI
- **Depends On:** Abdullah's 4.3. **Expected Output:** Recorded voice messages correctly flagged high-priority on delivery.

**ICP-4 (Your Role):** Demo messaging and calling end-to-end.

---

## Phase 5 — Medical Records, Vitals & Wearable Integration

#### 5.6 Medical records UI (list, upload, export)
- **Depends On:** Abdullah's 5.1. **Expected Output:** Records browsable, uploadable, and exportable as PDF from the app.

#### 5.7 Vitals entry UI
- **Depends On:** Abdullah's 5.3. **Expected Output:** Manual vitals entry works for both Dependent and Guardian.

#### 5.8 Wearable pairing UI (Dependent side)
- **Objective:** Build this against Abdullah's mocked sync endpoint first — don't wait on the wearable purchase.
- **Depends On:** Abdullah's 5.4; real device integration once Abdullah's 5.5 lands.
- **If Blocked, Contact:** Abdullah, once the real device is purchased and being integrated.
- **Expected Output Before Moving On:** Pairing flow works against mocked data now, real data later without UI rework.

**ICP-5 (Your Role):** Demo records/vitals UI; demo wearable pairing (live if the device is purchased by now, mocked otherwise — either is fine).

---

## Phase 6 — Directory, Marketplace, Camera & Security Hardening

#### 6.8 Directory/marketplace UI
- **Depends On:** Abdullah's 6.1, 6.2. **Expected Output:** Directory browsable, booking requests submittable.

#### 6.9 Camera view UI, live stream + on-screen viewing indicator (FR-K1.3)
- **Objective:** The privacy indicator is not optional polish — it must actually appear whenever a Guardian is viewing.
- **Depends On:** Abdullah's 6.3. **Expected Output:** Live stream renders; indicator visibly appears on the Dependent's device during viewing.

#### 6.10 Set up spare phone in camera mode (joint with Abdullah)
- **Objective:** Per the Hardware Document's suggestion — build this as your own app's "camera mode" rather than relying on a third-party app.
- **If Blocked, Contact:** Abdullah — joint task.
- **Expected Output Before Moving On:** Spare phone reliably streams to the Guardian app over local Wi-Fi.

**ICP-6 (Your Role):** Demo camera live view and directory/booking UI.

---

## Phase 7 — Analytics, Accessibility Polish, Localization Completion

#### 7.3 Analytics dashboard UI (charts)
- **Depends On:** Abdullah's 7.1. **Expected Output:** Adherence and vitals trends rendered as charts.

#### 7.4 Complete Urdu localization across every screen (FR-P4)
- **Objective:** Close out every remaining placeholder string from Task 1.10.
- **Depends On:** All prior UI tasks. **Expected Output:** No screen shows untranslated text in either language.

#### 7.5 Final accessibility pass: NFR-07 (2-tap), NFR-08 (contrast)
- **Depends On:** Sarim's 3.16 audit findings. **Reviewed By:** Sarim.
- **Expected Output Before Moving On:** All three Dependent Mode safety screens verified reachable within 2 taps, with compliant contrast.

**ICP-7 (Your Role):** Demo the analytics dashboard; confirm full localization and accessibility compliance with Sarim.

---

## Phase 8 — System Integration Testing & NFR Validation

#### 8.1 (You Support) End-to-end test pass across all 22 use cases
- **Led By:** Sarim. **Your Role:** Fix any frontend issues surfaced during testing.

#### 8.4 Bug-fixing sprint
- **Contact:** All — shared, triage together with Abdullah and Sarim.

**ICP-8 (Your Role):** Frontend stability confirmed for full demo dry-run.

---

## Phase 9 — Deployment

#### 9.4 Build release APK, install on demo devices
- **Depends On:** Abdullah's 9.3 (backend deployed to production).
- **If Blocked, Contact:** Abdullah, if production backend isn't live yet.
- **Expected Output Before Moving On:** Release APK installed and working against the production backend, not localhost.

#### 9.5 Smoke test production environment
- **Contact:** All — shared final check.

**ICP-9 (Your Role):** Confirm the release build works end-to-end against production.

---

## Phase 10 — Documentation & Demo Preparation

#### 10.4 / 10.5 Full rehearsal + final bug-fix buffer
- **Contact:** All — shared responsibility.

**ICP-10 (Final, Your Role):** Frontend fully stable and demoed live.

---

## Quick Reference: Who to Contact

| If you're blocked on... | Contact |
|---|---|
| An API not returning what you expect | Abdullah |
| A screen design/mockup you don't have yet | Sarim |
| The RTC SDK decision | Abdullah (joint decision, Task 4.1) |
| Wearable device specifics for integration | Abdullah (he coordinates with the purchase) |
| Accessibility/contrast sign-off | Sarim (Task 3.16) |
