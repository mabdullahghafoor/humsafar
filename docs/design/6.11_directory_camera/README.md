# 6.11 — High-fidelity mockups: healthcare directory, home-care booking, activity log, camera (v0.1 / v0.2)

**Task:** 6.11 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`. Same style as earlier sets. For Talha's Tasks **6.8** (directory / marketplace UI) and **6.9** (camera view + viewing indicator), and the camera-phone setup in **6.10**.

**Built from:** SRS v1.0 (FR-I1, FR-J1, FR-I2/J2, FR-K1, FR-K2, FR-N3, FR-O1) and the tables in migration 0001 (`healthcare_organizations`, `home_care_providers`, `booking_requests` with status starting at `pending`, `activity_log`, `camera_devices`, `camera_clips`, `audit_logs`). The Phase 6 API contracts did not exist yet. **v0.2 (21 Oct): 18 and 18b match `docs/api/directory_contract.md` (Task 6.1, PR #60) and use the style guide v0.2 colours.** 18c and 18d wait for Task 6.2 (booking + activity log); 19–19c, 29 and 29b wait for 6.3 / 6.4 (camera).

## What changed in v0.2
- 18 Directory: filter chips from `/organizations/types` (hospital, clinic, pharmacy, ambulance, emergency service, blood bank, laboratory); **Near you** with distances, nearest first; the **national emergency numbers** (Rescue 1122, Edhi 115, Chhipa 1020, Police 15; also Aman 1021 and Fire 16) always shown; **Sample** label on demo entries, whose Call button is disabled (the contract says the demo must not dial a sample number as real); no Call button when an entry has no phone.
- 18b Home care: chips from `/providers/specializations` (nurse, physiotherapist, attendant, doctor, lab technician); sort by charge; charge in PKR with its unit (visit / hour / day / month) or **Ask for price**; years of experience; Sample label.

## Guardian app

| # | Screen | Requirements |
|---|---|---|
| 18 | Directory, Emergency help — national numbers, nearby list with distance, type filter, search, Call (v0.2) | FR-I1 |
| 18b | Directory, Home care — specialization filter, sort by charge, PKR charge or Ask for price, Request (v0.2) | FR-J1 |
| 18c | Request a visit — for whom, date, time, reason, Send (status Pending) | FR-J1 |
| 18d | Activity log — calls to services and visit requests in one timeline | FR-I2/J2 |
| 19 | Camera live view — LIVE, timer, "Ammi can see that you are watching", Stop, Saved clips | FR-K1, FR-N3 |
| 19b | Saved clips — made automatically on Panic or Remote alarm, retention note | FR-K2, FR-O1 |
| 19c | Camera offline | FR-K1 |

## Dependent side

| # | Screen | Requirements |
|---|---|---|
| 29 | Dependent home **with the viewing indicator** bar at the top, shown the whole time a Guardian watches | **FR-K1.3** |
| 29b | Camera mode on the spare phone in the room — LIVE, who is watching, Wi-Fi and charging, exit with PIN | FR-K1, Task 6.10 |

## Notes for Talha
- **The viewing indicator (29) is a privacy requirement, not decoration.** It must appear every time a stream is open, on top of any Dependent screen, and disappear only when viewing stops. QA task 6.12 checks this with no exceptions.
- Camera access needs the **Camera viewing** permission (FR-A4). Without it, the Camera entry is hidden or shows the "Only Guardians with Camera permission" note.
- Every viewing is written to the audit log (FR-N3); the Primary can read it.
- Directory "Call" opens the phone dialer; the app records the call in the activity log (18d).
- Booking is **request only**: no payment in the app (FR-J3 payments are future scope). The provider confirms directly; the status then changes (Pending → Accepted → Done).

## Design choices open to discussion
1. **Directory data:** the backend ships 6 real national numbers (Edhi 115, Chhipa 1020, Aman 1021, Rescue 1122, Police 15, Fire 16); every other entry is a sample (`is_sample`) until real entries are collected (clarification 121).
2. **Clip length 30 s** is a suggestion; the SRS only says "short".
3. **Exit camera mode with a PIN** on the spare phone, so a visitor cannot switch it off by accident.
4. The viewing indicator uses **dark teal with a small red dot** (the dot follows the usual "recording" sign) rather than a full red bar, so it is not confused with Panic.
