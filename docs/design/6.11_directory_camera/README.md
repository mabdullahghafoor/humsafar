# 6.11 — High-fidelity mockups: healthcare directory, home-care booking, activity log, camera (v0.1)

**Task:** 6.11 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`. Same style as earlier sets. For Talha's Tasks **6.8** (directory / marketplace UI) and **6.9** (camera view + viewing indicator), and the camera-phone setup in **6.10**.

**Built from:** SRS v1.0 (FR-I1, FR-J1, FR-I2/J2, FR-K1, FR-K2, FR-N3, FR-O1) and the tables in migration 0001 (`healthcare_organizations`, `home_care_providers`, `booking_requests` with status starting at `pending`, `activity_log`, `camera_devices`, `camera_clips`, `audit_logs`). The Phase 6 API contracts did not exist yet. **If an endpoint differs, the screens will be updated (v0.2).**

## Guardian app

| # | Screen | Requirements |
|---|---|---|
| 18 | Directory, Emergency help — ambulance / blood bank / lab, search, filter, Call | FR-I1 |
| 18b | Directory, Home care — nurse / physio / attendant, fee, Request | FR-J1 |
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
1. **Directory data is placeholder.** Edhi (115) and Chhipa (1020) are real public numbers; all other names, home-care providers and fees are made up for the mockup and must be replaced by the seed data (6.1).
2. **Clip length 30 s** is a suggestion; the SRS only says "short".
3. **Exit camera mode with a PIN** on the spare phone, so a visitor cannot switch it off by accident.
4. The viewing indicator uses **dark teal with a small red dot** (the dot follows the usual "recording" sign) rather than a full red bar, so it is not confused with Panic.
