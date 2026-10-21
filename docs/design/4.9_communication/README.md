# 4.9 — High-fidelity mockups: messaging, urgent voice messages, calls (v0.1)

**Task:** 4.9 · **Owner:** Sarim · **Source:** Figma *Humsafar – App Design*, page `02 · App Designs (Hi-Fi)`, sections Guardian App and Dependent App. Same style as 1.12 / 3.9 / 2.8. For Talha's Tasks **4.6** (messaging UI), **4.7** (call UI + ZegoCloud) and **4.8** (urgent voice recorder).

Built against what is actually merged: `docs/api/messaging_contract.md` (4.2 text, 4.3 voice) and `docs/api/call_contract.md` (4.4 calls).

## Guardian app

| # | Screen | Requirements | Contract |
|---|---|---|---|
| 17 | Messages (inbox) — one row per Dependent, unread badge, urgent-voice preview | FR-E1, FR-E4 | `GET /messages/conversations` (`unread_count`, `total_unread` for the Chat tab badge) |
| 17b | Chat — text bubbles, read receipt, urgent voice bubble, "Sending…", "Not sent · Tap to retry", call / video buttons, mic button for urgent voice | FR-E1, FR-E4 | `GET/POST /messages`, `POST /messages/read`, `client_id` safe retry |
| 17c | Record urgent voice message — timer (max 2:00), waveform, warning that it rings as critical | FR-E4 | `POST /messages/voice` (1–120 s, max 2 MB) |
| 17d | Calls tab — history with Ended / Missed / Declined / Cancelled | FR-E2 | `GET /calls` (status, `duration_s`) |
| 17e | Calling (outgoing, ringing up to 30 s) | FR-E2 | `POST /calls`, poll `GET /calls/{id}` every ~2 s |
| 17f | In call (video) — mute, camera, speaker, end | FR-E2 | `join` → ZegoCloud SDK; `POST /calls/{id}/end` |
| 17g | Secondary without the Communication permission | FR-A4, FR-E1 | `403 MODULE_ACCESS_DENIED` |

## Dependent app (large text, few choices)

| # | Screen | Requirements | Contract |
|---|---|---|---|
| 25 | Messages — one big row per Guardian, each with its own **Call** button | FR-E1, FR-E2, FR-P1 | `GET /messages/conversations` |
| 25b | Chat with a Guardian — 17 px text, big "Call" bar, quick replies, **no mic** | FR-E1, FR-P1 | `POST /messages` |
| 25c | Urgent voice message received — big Play, "I heard it" | FR-E4 | `GET /messages/{id}/audio` (needs the login token), `POST /notifications/{id}/acknowledge` |
| 25d | Incoming call — large Answer / Decline, rings 30 s | FR-E2 | `POST /calls/{id}/accept` / `decline`; `incoming_call` push |

## Notes for Talha
- **Threads are per Guardian** (contract point 3): the Primary and a Secondary each have their own private chat with the Dependent. The inbox shows one row per person you can talk to.
- **Read receipts:** call `POST /messages/read` when the chat opens; show "Read" under my last bubble when `read_at` is set.
- **Safe retry:** make a new `client_id` (UUID) per message and reuse it when the user taps "Tap to retry". A `200` with `already_sent: true` means it was already delivered, so just mark it sent.
- **Text limit:** 1–2000 characters. Show a counter only after about 1800.
- **Urgent voice:** Guardian only. The Dependent app has no mic button (the backend answers `403 FORBIDDEN`). The audio download needs the auth header, so download first, then play.
- **Calls:** the server only rings and tracks the call. The audio/video screen (17f) comes from the ZegoCloud prebuilt Call UIKit, so style it close to this (dark teal, round buttons, red End). Caller polls every ~2 s while ringing. `USER_BUSY` → show "Ammi is on another call". `missed` / `declined` → back to the chat with a short message.
- **Permissions:** if the Primary turns Communication off, the Secondary's thread disappears and 17g is shown when opening it from a notification or link. Panic is not affected.
- Bottom nav "Chat" tab = 17 / 17d, with the `total_unread` badge.

## Design choices open to discussion
1. **Urgent voice uses amber, not red.** Red stays for Panic and critical alerts (style rule). Amber still stands out from normal teal messages.
2. **Hang-up and Decline buttons are red.** This is the one place red is used outside Panic, because every phone uses red for hang-up and older users expect it.
3. **Quick replies on the Dependent chat** ("I am fine", "Call me", "Yes", "No") send normal text messages. They are a design idea only; the backend needs no change.
4. **"Ask Ali for access" (17g)** has no backend endpoint yet. It could send a normal message to the Primary, or be removed.
5. Call screens are full screen without the app bar, so **Aa / EN|UR are not shown there** (they follow the setting chosen elsewhere).
