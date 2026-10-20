# 2.10 / 3.18 — Updated architecture and new workflow diagrams

**Tasks:** 2.10 and 3.18 (continue / update diagrams), covering everything merged up to Phase 4 · **Owner:** Sarim · Each diagram is a PNG (slides, report) plus an SVG (editable: Figma, Inkscape or draw.io). Same style as `../1.14_diagrams/`.

| # | Diagram | Version | Based on |
|---|---|---|---|
| D1 | System Architecture (as built, Phases 1–4) | **v0.2** (replaces v0.1 in 1.14) | code on `dev`, migrations 0001–0011 |
| D6 | Workflow — Panic Mode and Remote alarm | v0.1 | `panic_contract.md`, `alarm_contract.md` |
| D7 | Workflow — Wellness check "Are you OK?" | v0.1 | `wellness_contract.md` |
| D8 | Workflow — Location, safe zones and device health | v0.1 | `location_contract.md`, `geofence_contract.md`, `device_health_contract.md` |
| D9 | Workflow — Messages and urgent voice messages | v0.1 | `messaging_contract.md` |
| D10 | Workflow — Voice / video call lifecycle | v0.1 | `call_contract.md` |

D3 (onboarding), D4 (escalation chain) and D5 (medication) in `../1.14_diagrams/` are still correct and are not repeated here.

## What changed in D1 (v0.1 → v0.2)
- **Communication** module is now built (text, urgent voice, calls).
- Database migrations now **0001–0011**.
- **File storage** exists: voice messages are kept in a server folder (`VOICE_STORAGE_DIR`); records and clips come in Phases 5–6.
- RTC decided: **ZegoCloud** (Task 4.1), with a mock join token until the real keys are wired in.
- Background scheduler also runs the **missed-call** sweep.

## Documentation drift (for Task 7.6)
Still open from 1.14: Kotlin → Flutter, Node.js → FastAPI, IP camera → spare phone, Redis not used (in-process scheduler instead).
New: SDS 6.2 / Figure 6.1 show **object storage**; built so far is a **local server folder** for voice files (can move to a cloud bucket later without changing the API).
