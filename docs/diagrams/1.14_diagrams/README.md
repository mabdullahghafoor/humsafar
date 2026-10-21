# 1.14 — Architecture and workflow diagrams (v0.1)

**Task:** 1.14 · **Owner:** Sarim · Each diagram is a PNG (for slides and documents) plus an SVG (editable source: opens in Figma, Inkscape or draw.io).

| # | Diagram | Based on |
|---|---|---|
| D1 | System Architecture (as built, Phases 1–3) | SDS 5, 6, 7.1, 8 + the code on `dev` |
| D2 | Deployment (target for Phase 9) | SDS 16 + Roadmap Phase 9 (Render) |
| D3 | Workflow — Registration, KYC and Guardian linkage | `docs/api/` auth, kyc, linkage, permissions contracts |
| D4 | Workflow — Alert escalation chain | `docs/api/escalation_contract.md`, `emergency_contact_contract.md`, `panic_contract.md` |
| D5 | Workflow — Medication dose | `docs/api/medication_contract.md` |

Colour key (D1, D2): green = built and merged · grey dashed = planned · yellow = external service (mocked today) · purple = local hardware.

## Documentation drift found (for Task 7.6, full documentation refresh)
The locked SDS figures no longer match what is built. These diagrams replace them for the presentation; the SDS itself is not changed here.
- **SDS Figure 6.1** shows the apps as *Android — Kotlin*. Built: **Flutter** (stack change accepted earlier).
- **SDS Figure 16.1** shows a *Node.js API* server cluster, an *IP camera*, and has overlapping boxes. Built/decided: **FastAPI** on Render, **spare phone in camera mode** (Hardware document).
- SDS 6.2 / Figure 6.1 show **Redis** (cache/queue) and **object storage**. Built so far: an in-process background scheduler (runs every minute) instead of Redis; no file storage yet (needed from Phase 5).

Update these diagrams when a phase changes the picture (Task 2.10 and 3.18: "continue/update diagrams").
