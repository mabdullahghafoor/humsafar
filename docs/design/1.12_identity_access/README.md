# 1.12 — High-fidelity mockups: Identity & Access (v0.1)

**Task:** 1.12 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)` (link in `../README.md`). Built on the 0.7 wireframes.

| # | Screen | Used by | Requirements | Section in Figma |
|---|---|---|---|---|
| 00 | Style guide (colours, type, buttons, rules) | — | NFR-07, NFR-08 | Components & Styles |
| 01 | Welcome (role choice) | both | FR-A1 | Guardian App |
| 02 | Log in (incl. error state) | both | FR-A1 | Guardian App |
| 03 | Create account (incl. field validation states) | both | FR-A1 | Guardian App |
| 04 | Verify identity — CNIC + live photo | Dependent | FR-A2 | Dependent App |
| 05 | Share my ID (QR + copy/share) | Dependent | FR-B1 | Dependent App |
| 06 | Verify your account — phone OTP + CNIC | Guardian | FR-A3 | Guardian App |
| 09 | Link a Dependent (scan or type ID) | Primary Guardian | FR-B1, FR-B2 | Guardian App |
| 10 | Permissions per Secondary Guardian | Primary Guardian | FR-A4 | Guardian App |

## Design direction (decided 2026-10-19)
- **Colours:** calm teal-blue. Primary `#0E7490`, dark `#155E75`, tint `#ECFEFF`; text `#0F172A`, muted `#64748B`, border `#CBD5E1`; success `#15803D`, warning `#B45309`. **Red `#DC2626` is reserved for Panic and critical alerts only.**
- **Type:** Inter — title 26 bold, heading 18 bold, body 15, caption 12.
- **Components:** buttons 54 px tall, 14 px radius; inputs 50 px, 12 px radius; touch targets at least 48 × 48; text contrast at least 4.5 : 1 (WCAG 2.1 AA).
- Every app bar keeps the **Aa** (large text / high contrast) toggle and the **EN|UR** language switch (team UI convention).

## Notes for Talha (Task 2.5)
- Field rules shown match the contracts: CNIC `12345-1234567-1`, Pakistani phone, password at least 8 characters.
- Log in shows one message for wrong email and wrong password (by design, auth contract).
- Screen 05/09: the Dependent's `user_id` is shared as QR or text (linkage contract §3).
- The logo is a **placeholder** until the team picks one.
