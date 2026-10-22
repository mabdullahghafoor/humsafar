# 2.10 / 3.18 — Updated architecture and new workflow diagrams

**Tasks:** 2.10 and 3.18 (continue / update diagrams), covering everything merged up to Phase 4 (D1: up to Phase 7) · **Owner:** Sarim · Each diagram is a PNG (slides, report) plus an SVG (editable: Figma, Inkscape or draw.io). Same style as `../1.14_diagrams/`.

| # | Diagram | Version | Based on |
|---|---|---|---|
| D1 | System Architecture (as built, Phases 1–7) | **v0.4** (replaces v0.3; v0.1 in 1.14) | code on `dev` up to PR #80, migrations 0001–0022 |
| D6 | Workflow — Panic Mode and Remote alarm | v0.1 | `panic_contract.md`, `alarm_contract.md` |
| D7 | Workflow — Wellness check "Are you OK?" | v0.1 | `wellness_contract.md` |
| D8 | Workflow — Location, safe zones and device health | v0.1 | `location_contract.md`, `geofence_contract.md`, `device_health_contract.md` |
| D9 | Workflow — Messages and urgent voice messages | v0.1 | `messaging_contract.md` |
| D10 | Workflow — Voice / video call lifecycle | v0.1 | `call_contract.md` |

D3 (onboarding), D4 (escalation chain) and D5 (medication) in `../1.14_diagrams/` are still correct and are not repeated here.

## What changed in D1 (v0.3 → v0.4)
- All eight modules are built: **Directory & Marketplace** (requests, Activity Timeline, 6.2) and **Security & Surveillance** (camera, clips, audit log, retention, 6.3–6.7).
- **Medication & Records** also holds analytics and summary reports (7.1, 7.2).
- Interface: HSTS / https-only option and rate limits (429) from 6.5.
- Database: 33 tables, migrations **0001–0022**. File storage also holds camera clips and reports, encrypted.
- Scheduler also runs camera sessions, clip expiry, account retention and summary reports.
- ZegoCloud carries calls **and** the camera video (in-transit encryption, not end-to-end; drift D-38).

## What changed in D1 (v0.2 → v0.3)
- **Medication & Records** now also holds the medical vault, appointments, vitals and band sync (Tasks 5.1–5.4).
- **Directory & Marketplace** partly built: directory and home-care providers (6.1); bookings and the activity log come with 6.2.
- Database migrations now **0001–0016** (30 tables).
- **File storage** now also holds medical-record files, encrypted at rest (AES-256-GCM).
- Public read-only **doctor link** (72 h) on the API; the Dependent app sends **band batches** (mock data until the real band, 5.5).
- Scheduler also runs the **band no-data** sweep and **appointment reminders**.
- ZegoCloud now uses the **real token** (4.4b).

## What changed in D1 (v0.1 → v0.2)
- **Communication** module is now built (text, urgent voice, calls).
- Database migrations now **0001–0011**.
- **File storage** exists: voice messages are kept in a server folder (`VOICE_STORAGE_DIR`); records and clips come in Phases 5–6.
- RTC decided: **ZegoCloud** (Task 4.1), with a mock join token until the real keys are wired in.
- Background scheduler also runs the **missed-call** sweep.

## Documentation drift (for Task 7.6)
Still open from 1.14: Kotlin → Flutter, Node.js → FastAPI, IP camera → spare phone, Redis not used (in-process scheduler instead).
New: SDS 6.2 / Figure 6.1 show **object storage**; built so far is a **local server folder** for voice files (can move to a cloud bucket later without changing the API).
