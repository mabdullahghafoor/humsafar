# Humsafar — Individual Handbook: Syed Sarim Jawad Zaidi
### Role: UI/UX Design, Documentation, Workflow/Architecture Diagrams, Testing, Presentation

**Source of truth:** This handbook is extracted directly from the Master Development Roadmap v1.0. Task numbers match the Master Roadmap exactly. If this handbook and the Master Roadmap ever disagree, the Master Roadmap wins — flag the mismatch.

**Your position in the workflow:** Your design work runs *ahead* of Talha's builds throughout this project — that's a deliberate anti-bottleneck design, not a coincidence. Your QA/testing and documentation work runs *behind* each phase, confirming what was actually built. Both roles matter equally.

---

## Phase 0 — Environment Setup

#### 0.6 Set up shared documentation/design workspace
- **Deliverable:** Figma (or equivalent) workspace, documentation folder structure, shared with the team.
- **Depends On:** Nothing — start immediately.
- **Expected Output Before Moving On:** Abdullah and Talha both have access.

#### 0.7 Low-fidelity wireframes for all screens (SDS Section 10.1 screen list)
- **Objective:** Give Talha something to build from as early as possible.
- **Depends On:** 0.6.
- **Expected Output Before Moving On:** Every screen listed in SDS 10.1 has at least a rough wireframe.

**ICP-0 (Your Role):** Present the full wireframe set alongside Abdullah's backend skeleton and Talha's Flutter skeleton.

---

## Phase 1 — Identity & Access

#### 1.12 High-fidelity mockups for Identity & Access screens
- **Depends On:** 0.7. **Expected Output:** Polished, ready-to-build mockups for registration/login/KYC/permission screens.

#### 1.13 Draft project-wide test plan / QA checklist template
- **Objective:** Build the template now so every later phase has a consistent QA structure to test against.
- **Depends On:** Nothing — independent work.
- **Expected Output Before Moving On:** A reusable checklist format covering functional correctness, accessibility, and security spot-checks.

#### 1.14 Begin architecture/workflow diagrams for the final presentation
- **Objective:** Get a head start by reusing SDS diagrams as your base rather than starting from scratch later.
- **Depends On:** Nothing — independent work.

**ICP-1 (Your Role):** Test the full register → KYC → link → permissions flow against your QA checklist once Talha and Abdullah demo it.

---

## Phase 2 — Location, Geofencing, Device Health

#### 2.8 High-fidelity mockups: Live Map, Geofence config, Dependent Mode home
- **Depends On:** 0.7. **Expected Output:** Mockups ready before Talha starts building the Live Map screen (his Task 2.6).

#### 2.9 QA pass on Phase 1 deliverables
- **Depends On:** ICP-1. **Expected Output:** Documented pass/fail results against your Task 1.13 checklist.

#### 2.10 Continue architecture/workflow diagrams
- **Depends On:** 1.14, ongoing.

**ICP-2 (Your Role):** No blocking role in the BLE spike review — that's Abdullah's — but confirm the Live Map + geofence demo passes your QA checklist.

---

## Phase 3 — The Core Safety Loop (Your Mockups Come First in This Phase)

#### 3.9 High-fidelity mockups for all Dependent Mode screens + Guardian alert/config screens
- **Objective:** This is the most important sequencing point for you in the whole project — do this at the very start of Phase 3, before Talha needs it, not alongside him.
- **Depends On:** 0.7.
- **Expected Output Before Moving On:** Talha has everything he needs to build Panic Mode, Wellness Check, and Medication Confirmation screens without waiting on you mid-phase.

#### 3.16 Accessibility audit: 2-tap rule (NFR-07), contrast ratios (NFR-08)
- **Depends On:** Talha's 3.11-3.13 (built screens to audit).
- **Expected Output Before Moving On:** Documented findings on tap-count and contrast compliance, fed back to Talha's Task 7.5.

#### 3.17 QA test cases for the full escalation chain
- **Objective:** Write test cases covering the simulated missed-check → escalation → external-contact path.
- **Depends On:** Abdullah's 3.5, 3.8.
- **Expected Output Before Moving On:** Test cases ready to run at ICP-3.

#### 3.18 Documentation/diagram updates reflecting Phase 3
- **Depends On:** Ongoing.

**ICP-3 (Your Role) — the most important checkpoint in the project:** Run your escalation-chain test cases live against Abdullah's backend and Talha's UI — Panic Mode, Wellness Check escalation, and medication confirmation, in one sequence.

---

## Phase 4 — Communication & Notifications Completion

#### 4.9 Mockups for communication screens
- **Depends On:** Early in phase, ahead of Talha's 4.6-4.8.

#### 4.10 QA: messaging + calling flows
- **Depends On:** Talha's 4.6-4.8. **Expected Output:** Documented pass/fail on message delivery and call reliability.

**ICP-4 (Your Role):** Confirm messaging/calling passes QA.

---

## Phase 5 — Medical Records, Vitals & Wearable Integration

#### 5.9 Mockups for records/vitals/wearable screens
- **Depends On:** Early in phase, ahead of Talha's 5.6-5.8.

#### 5.10 QA: records/export/vitals flows
- **Depends On:** Talha's 5.6-5.7.

#### 5.11 Update the Hardware Selection & Integration Document with final wearable specs
- **Objective:** Once the team finishes their market comparison and purchases a device, this document needs updating from "OPEN" to a locked, specific entry.
- **Depends On:** The team's wearable purchase decision.
- **If Blocked, Contact:** Abdullah — coordinate on the exact model and confirmed GATT services before writing this up.
- **Expected Output Before Moving On:** Hardware document reflects the real, final device — not the reference candidates.

**ICP-5 (Your Role):** QA records/vitals; confirm hardware documentation is current.

---

## Phase 6 — Directory, Marketplace, Camera & Security Hardening

#### 6.11 Mockups for directory/camera screens
- **Depends On:** Early in phase, ahead of Talha's 6.8-6.9.

#### 6.12 QA: camera + directory flows
- **Objective:** Specifically verify the on-screen viewing indicator (FR-K1.3) actually appears — this is a privacy requirement, not cosmetic.
- **Depends On:** Talha's 6.9.
- **Expected Output Before Moving On:** Confirmed the indicator appears every time a Guardian views the stream, with no exceptions.

#### 6.13 Security review pass (paired with Abdullah)
- **Depends On:** Abdullah's 6.5, 6.6.
- **If Blocked, Contact:** Abdullah — this is a paired task.

**ICP-6 (Your Role):** Confirm camera privacy indicator and directory/booking flows pass QA.

---

## Phase 7 — Analytics, Accessibility Polish, Localization Completion

#### 7.6 Full documentation refresh
- **Objective:** Confirm SRS/SDS/Reference Guide/Hardware doc still match what was actually built across all six prior phases; flag any drift rather than letting documentation silently go stale.
- **Depends On:** All prior phases.
- **Expected Output Before Moving On:** A short list of any documentation-vs-implementation mismatches, resolved or explicitly logged.

#### 7.7 QA regression pass across all modules
- **Depends On:** All prior phases.

**ICP-7 (Your Role):** Confirm documentation accuracy and full regression pass before entering system-wide testing.

---

## Phase 8 — System Integration Testing & NFR Validation

#### 8.1 End-to-end test pass across all 22 use cases (You Lead)
- **Objective:** This is your phase to lead — Abdullah and Talha support you.
- **Depends On:** ICP-7.
- **Expected Output Before Moving On:** Every one of the 22 use cases from the SRS tested and confirmed working.

#### 8.4 Bug-fixing sprint
- **Contact:** All — shared, triage together.

**ICP-8 (Your Role):** Confirm full system readiness for the first demo dry-run.

---

## Phase 9 — Deployment

#### 9.5 Smoke test production environment
- **Contact:** All — shared final check, after Abdullah's 9.3 and Talha's 9.4 are both done.

**ICP-9 (Your Role):** Confirm production environment passes a final sanity check.

---

## Phase 10 — Documentation & Demo Preparation (Your Phase to Lead)

#### 10.1 Final consistency check across all project documents
- **Depends On:** ICP-9. **Expected Output:** SRS, SDS, Reference Guide, Hardware Document, and Master Roadmap all confirmed consistent with the final build.

#### 10.2 Presentation slides
- **Depends On:** 10.1.

#### 10.3 Demo script — joint with Abdullah
- **Objective:** Plan feature order, timing, and a fallback plan if hardware misbehaves live.
- **If Blocked, Contact:** Abdullah.

#### 10.4 / 10.5 Full rehearsal + final bug-fix buffer
- **Contact:** All — shared responsibility.

**ICP-10 (Final, Your Role):** Lead the final rehearsal and confirm the team is ready to present.

---

## Quick Reference: Who to Contact

| If you're blocked on... | Contact |
|---|---|
| A feature not working as documented (for QA purposes) | Abdullah (backend) or Talha (frontend), depending on where the issue is |
| Wearable model/specs for the hardware doc update | Abdullah |
| Security review pairing | Abdullah |
| Demo script planning | Abdullah |
