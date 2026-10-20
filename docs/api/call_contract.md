# Calls contract (Task 4.4, FR-E2)

For Talha (call screens + ZegoCloud SDK, task 4.7) and Sarim (QA cases). Voice and video calls between a Guardian and a linked Dependent.

## The idea in 8 lines
1. The audio / video travel through the ZegoCloud SDK (decision 4.1). Our server only manages the **call**: who is calling whom, ringing, accept / decline / end, history, and the **join token** for the SDK.
2. A Guardian calls a linked Dependent, or a Dependent calls a linked Guardian. Guardian to Guardian and Dependent to Dependent are refused (`403 NOT_LINKED_TO_DEPENDENT`).
3. The **Primary** can always call. A **Secondary** needs the `communication` permission, in both directions, also to accept.
4. Starting a call **rings** the other person: a **critical** `incoming_call` notification + high-priority push (`data.call_id`, `data.call_type`, `data.caller_id`, `data.expires_at`).
5. **The callee must accept** (FR-E2). Only the callee can accept or decline. The callee gets `join` only after accepting. The caller gets `join` at once and can enter the room while it rings.
6. Not answered within **30 seconds**: the call becomes `missed`, and the callee gets a standard `missed_call` notification. The same happens if the caller hangs up while it rings (`cancelled`).
7. **One open call per person.** Calling the same person again while it rings returns the same call (`200`, `already_active: true`). Any other clash is `409 USER_BUSY`.
8. Every action is safe to repeat (accept, decline, end).

## Status of a call
`ringing` -> `accepted` -> `ended` | `ringing` -> `declined` | `cancelled` | `missed`
A call still running after 1 hour is ended by the server.

## The call object
`{ call_id, caller_id, callee_id, type: "voice"|"video", status, started_at, answered_at, ended_at, duration_s, from_me, other_name, already_active, ring_expires_at, join }`
`join` = `{ provider, app_id, room_id, user_id, token, expires_at }`: give `app_id`, `room_id`, `user_id` and `token` to the ZegoCloud SDK. Do not log the token. If `join` is null when it should not be (the provider hiccuped), call `GET /calls/{id}` again.

## Endpoints
| Method and path | Who | What |
|---|---|---|
| POST `/calls` | linked Guardian / Dependent | Body `{ "callee_id": "<id>", "type": "voice" }` (`voice` default, or `video`). `201` new, `200` if the same call is already open |
| GET `/calls/{id}` | caller or callee | The state. **The caller polls this about every 2 s while it rings** (the SDK also shows when the other person joins) |
| POST `/calls/{id}/accept` | callee only | Accept. Reply has `join` |
| POST `/calls/{id}/decline` | callee only | Say no |
| POST `/calls/{id}/end` | caller or callee | Hang up: ringing + caller = `cancelled`; ringing + callee = `declined`; answered = `ended` with `duration_s` |
| GET `/calls?limit=30&before=<datetime>` | me | My calls, newest first. `next_before` for the next page |

## Errors
| Code | Status | When |
|---|---|---|
| `NOT_AUTHENTICATED` | 401 | no / bad token |
| `NOT_LINKED_TO_DEPENDENT` | 403 | not linked, unknown user, same role, or yourself |
| `MODULE_ACCESS_DENIED` | 403 | Secondary without `communication` (also when it is taken away while ringing) |
| `GUARDIAN_NOT_VERIFIED` | 403 | the Guardian side is not verified |
| `FORBIDDEN` | 403 | the caller tries to accept / decline their own call |
| `CALL_NOT_FOUND` | 404 | unknown id, or not your call |
| `USER_BUSY` | 409 | you or the other person is in another open call |
| `CALL_NOT_RINGING` | 409 | accept / decline after it was answered, declined, missed or cancelled (details: `status`) |
| `VALIDATION_ERROR` | 422 | bad `type`, bad id, bad `limit` |

## Notifications
| type | priority | to | when |
|---|---|---|---|
| `incoming_call` | critical | the callee | a call starts |
| `missed_call` | standard | the callee | it timed out, or the caller hung up before an answer |

## Provider and keys
`CALL_PROVIDER=mock` (default) gives a fake token so the whole flow can be tested without ZegoCloud. `CALL_PROVIDER=zego` gives a **real ZegoCloud token04** (checked against ZegoCloud's own open-source generator): `join.provider` = `zego`, `join.app_id` is the project's App ID, `join.token` lets that person log in to **that one room** and publish a stream. The Server Secret stays only in the backend `.env` and is never sent to the app. Settings: `CALL_PROVIDER`, `ZEGO_APP_ID`, `ZEGO_SERVER_SECRET` (in your own `.env`, see `backend/.env.example`), `CALL_RING_S` (30), `CALL_MAX_S` (3600), `CALL_TOKEN_TTL_S` (3600).

**For Talha (4.7):** use the `join` values with the ZegoCloud SDK: `app_id` (a string, convert to a number if the SDK wants one), `user_id`, `room_id`, `token`. Ringing comes from OUR critical `incoming_call` notification and the call state from OUR endpoints, so please do not also use ZegoCloud's own call-invitation ringing, or the phone will ring twice. Use the SDK only for the audio / video once `join` is given.

## Not in this task
Multi-Guardian bridge call (FR-E5, optional) is Task 4.5.
