# 6.11 — High-fidelity mockups: healthcare directory, home-care booking, activity log, camera (v0.1 / v0.2)

**Task:** 6.11 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`. Same style as earlier sets. For Talha's Tasks **6.8** (directory / marketplace UI) and **6.9** (camera view + viewing indicator), and the camera-phone setup in **6.10**.

**Built from:** SRS v1.0 (FR-I1, FR-J1, FR-I2/J2, FR-K1, FR-K2, FR-N3, FR-O1) and the tables in migration 0001 (`healthcare_organizations`, `home_care_providers`, `booking_requests` with status starting at `pending`, `activity_log`, `camera_devices`, `camera_clips`, `audit_logs`). The Phase 6 API contracts did not exist yet. **v0.2 (21–22 Oct): 18 and 18b match `docs/api/directory_contract.md` (Task 6.1, PR #60); 18c, 18d and the new 18e match `docs/api/booking_contract.md` (Task 6.2, PR #67). 19, 19b, 19c, the new 19d, 29 and 29b match `docs/api/camera_contract.md` (Tasks 6.3 and 6.4, PR #70, #72). All use the style guide v0.2 colours.**

## What changed in v0.2
- 19 Camera: "2 of 3 watching" (at most 3 viewers), banner "Ammi can see who is watching" (her phone shows the names), Emergency clips button, notes on the 3-viewer limit and the audit log.
- 19b **Emergency clips** (was Saved clips): 20-second clips recorded by the room phone on Panic or Remote alarm; status **Saved** or **Missed** (room phone offline or no upload within 3 minutes); opening a clip is audited; only the Dependent or the Primary can delete.
- 19c Camera offline: from `409 CAMERA_OFFLINE` with the last seen time.
- **New 19d No camera set up yet** (`409 NO_CAMERA`): three set-up steps on the spare phone; note for `409 TOO_MANY_VIEWERS` ("Camera busy, try again shortly"); only the Dependent or the Primary can pair.
- 29 Dependent home: the viewing notice names **everyone** watching ("Ali and Sara are watching your camera") with start times (`GET .../camera/viewing`).
- 29b Camera mode: video is sent only while someone watches; a red bar while an **emergency clip** is recording (12 / 20 s).
- 18c Request a visit: provider card (name, specialization, PKR charge, Sample label); optional wished day and time; optional note (300 characters); banner "Nothing is sent to the provider"; button **Save request** (the request is a note of intent for the family).
- **New 18e Visit request:** status chip, wished time, note, who asked (name and role) and when; the provider's phone with **Call** (disabled for sample entries); **Mark as confirmed / Mark as completed / Cancel request**, shown only to the person who asked and the Primary.
- 18d Activity log: one timeline for everyone (Dependent too), newest first; filters All / Calls / Requests; each line says who (name and role); request lines carry the request's **current** status chip (Pending / Confirmed / Completed / Cancelled; "Accepted" and "Done" are gone); "Called" means Call was tapped (the call itself is not recorded).
- 18 Directory: filter chips from `/organizations/types` (hospital, clinic, pharmacy, ambulance, emergency service, blood bank, laboratory); **Near you** with distances, nearest first; the **national emergency numbers** (Rescue 1122, Edhi 115, Chhipa 1020, Police 15; also Aman 1021 and Fire 16) always shown; **Sample** label on demo entries, whose Call button is disabled (the contract says the demo must not dial a sample number as real); no Call button when an entry has no phone.
- 18b Home care: chips from `/providers/specializations` (nurse, physiotherapist, attendant, doctor, lab technician); sort by charge; charge in PKR with its unit (visit / hour / day / month) or **Ask for price**; years of experience; Sample label.

## Guardian app

| # | Screen | Requirements |
|---|---|---|
| 18 | Directory, Emergency help — national numbers, nearby list with distance, type filter, search, Call (v0.2) | FR-I1 |
| 18b | Directory, Home care — specialization filter, sort by charge, PKR charge or Ask for price, Request (v0.2) | FR-J1 |
| 18c | Request a visit — for whom, optional wished time and note, Save request (v0.2) | FR-J1 |
| 18e | Visit request — status, details, Call to arrange, Confirm / Complete / Cancel (new, v0.2) | FR-J1 |
| 18d | Activity log — calls and visit requests in one timeline, who did it, current status, filters (v0.2) | FR-I2/J2 |
| 19 | Camera live view — LIVE, timer, viewers 2 of 3, "Ammi can see who is watching", Stop, Emergency clips (v0.2) | FR-K1, FR-N3 |
| 19b | Emergency clips — 20 s on Panic or Remote alarm, Saved / Missed, audit note, who may delete (v0.2) | FR-K2, FR-O1 |
| 19c | Camera offline — last seen (v0.2) | FR-K1 |
| 19d | No camera set up yet — set-up steps, camera busy note (new, v0.2) | FR-K1 |

## Dependent side

| # | Screen | Requirements |
|---|---|---|
| 29 | Dependent home **with the viewing indicator** bar at the top, naming everyone watching (v0.2) | **FR-K1.3** |
| 29b | Camera mode on the spare phone — LIVE, who is watching, emergency clip recording, Wi-Fi and charging, exit with PIN (v0.2) | FR-K1, FR-K2, Task 6.10 |

## Notes for Talha
- **The viewing indicator (29) is a privacy requirement, not decoration.** It must appear every time a stream is open, on top of any Dependent screen, and disappear only when viewing stops. QA task 6.12 checks this with no exceptions.
- Camera access needs the **Camera viewing** permission (FR-A4). Without it, the Camera entry is hidden or shows the "Only Guardians with Camera permission" note.
- Every viewing is written to the audit log (FR-N3); the Primary can read it.
- Directory "Call" first sends `POST /dependents/{id}/directory/contacts`, then opens the phone dialer (the call itself is not recorded).
- Booking is **request only**: nothing is sent to the provider and there is no payment (FR-J3 payments are future scope). The family keeps the status: Pending → Confirmed → Completed, or Cancelled; only the person who asked or the Primary may change it (`booking_contract.md`).

## Design choices open to discussion
1. **Directory data:** the backend ships 6 real national numbers (Edhi 115, Chhipa 1020, Aman 1021, Rescue 1122, Police 15, Fire 16); every other entry is a sample (`is_sample`) until real entries are collected (clarification 121).
2. **Clip length:** 20 s, fixed by the contract (clarification 143).
3. **Exit camera mode with a PIN** on the spare phone, so a visitor cannot switch it off by accident.
4. **Requests and the timeline use the `health_records` permission** for a Secondary (clarification 129, to confirm with the team).
5. The viewing indicator uses **dark teal with a small red dot** (the dot follows the usual "recording" sign) rather than a full red bar, so it is not confused with Panic.

## Colour update (30 Oct 2026)
All screens in this folder now use the **style guide v0.2 colours**: old red `#DC2626` → `#B91C1C` and old grey `#64748B` → `#475569` (NFR-08 contrast fix). **Colours only, no layout or text change.** Updated screens:

| # | Screen | Version |
|---|---|---|
| 19 | Camera | v0.2 → **v0.3** |
| 19b | Emergency clips | v0.2 → **v0.3** |
| 29b | Camera mode | v0.2 → **v0.3** |

Overview rebuilt from the latest versions: v0.2 → **v0.3**. Editable SVG sources of every screen in this folder are in `svg/` (same names as the PNGs, `.svg`); use them for Figma import.
