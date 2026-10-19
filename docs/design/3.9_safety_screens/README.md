# 3.9 — High-fidelity mockups: Dependent Mode + Guardian alert screens (v0.1)

**Task:** 3.9 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`. Same style as 1.12 (see `../1.12_identity_access/README.md`).

## Dependent Mode (for Talha's 3.10 – 3.13)
| # | Screen | Requirements | Contract |
|---|---|---|---|
| 20 | Home — the 3 safety actions, one tap each | FR-P1, NFR-07 | — |
| 21 | Panic — press and hold 2 s | FR-D2 | `panic_contract.md` |
| 21b | Help is coming — who was told, "I am safe now" | FR-D2 | `panic_contract.md` (resolve) |
| 22 | Wellness check — "Are you OK?" with countdown | FR-D4 | `wellness_contract.md` |
| 23 | Medicine time — step 1 "I took it" | FR-F1.3 | `medication_contract.md` |
| 23b | Confirm medicine — step 2 + taken state | FR-F1.3 | `medication_contract.md` |
| 24 | Alarm ringing — stop / call | FR-D3 | `alarm_contract.md` |

## Guardian (for Talha's 3.14, 3.15)
| # | Screen | Requirements | Contract |
|---|---|---|---|
| 07 | Home — panic banner, status tiles, alerts, quick actions | FR-B4.2, FR-M1 | `notification_contract.md` |
| 08 | Alerts — open alerts with chain level, "I've seen it" | FR-M2, FR-D5 | `escalation_contract.md` |
| 08b | Missed dose — what happens next, extend / escalate | FR-D1 | `medication_contract.md` |
| 13 | Care schedules — medicines | FR-F1 | `medication_contract.md` |
| 13b | Wellness check times + grace period | FR-D4 | `wellness_contract.md` |
| 14 | Emergency settings — remote alarm (Primary only) + external contact | FR-D3, FR-R1 | `alarm_contract.md`, `emergency_contact_contract.md` |

## Design choices to note (Talha can push back)
- **Panic is press-and-hold for 2 s** on screen 21 to stop accidental alerts. Home → Panic → hold stays within the 2-tap rule (NFR-07). The server call is still the single `POST /panic`.
- **Wellness "I need help"** opens the Panic screen (no separate endpoint needed).
- **Missed dose "Give more time"** uses the contract default of 30 min (`extend`, 5–120 allowed); "Tell other Guardians now" = `escalate`.
- **"I've seen it"** = acknowledge; it stops the escalation chain.
- Red is used only for Panic and critical states. Dependent screens use 22–38 px text and 96–200 px tall buttons.
