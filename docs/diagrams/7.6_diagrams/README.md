# 7.6 — Architecture and deployment diagrams, November 2026

**Task:** 7.6 (documentation refresh) · **Owner:** Sarim · Each diagram is a PNG (slides, report) plus an SVG (editable: Figma, Inkscape or draw.io). Same style as `../1.14_diagrams/` and `../3.18_diagrams/`.

| # | Diagram | Version | Based on |
|---|---|---|---|
| D1 | System Architecture (as built, Phases 1–7) | **v0.5** (replaces v0.4) | code on `dev`, migrations 0001–0022, QA results up to `debug-apk-1.9.5` |
| D2 | Deployment (as deployed) | **v0.2** (replaces the Phase 9 target, v0.1 in 1.14) | staging server on Render, QA retests, Drift Register v0.10 |

## What changed in D1 (v0.4 → v0.5)
- Push is **real** since 9 Nov (Firebase FCM; F-16 fixed on the server). SMS (code 123456, D-44) and KYC are still mock; ZegoCloud carries calls and camera video with a real token.
- Dependent App has four safety actions (Panic, I am OK, My medicine, Messages).
- Band: the Bluetooth side of the app is built (26 Nov, against Abdullah's 9-byte packet spec); not tested on the band yet.
- File storage: on the server disk, lost on every redeploy of Render's free plan (F-26, open).
- The modules, tables (33) and migrations (0001–0022) are unchanged.

## What changed in D2 (v0.1 → v0.2)
- Shows what is running: Render web service (Free, Singapore, branch `dev`), Render Postgres `humsafar-db-2` (valid to 24 Dec 2026), UptimeRobot on `/health`, debug APKs published as GitHub Releases.
- Third-party boxes marked real or mock; ZegoCloud added as built.
- Spare phone (6.10) not set up; signed release build still to do.
