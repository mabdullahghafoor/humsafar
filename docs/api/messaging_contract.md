# Messaging contract (Task 4.2 text, Task 4.3 voice; FR-E1, FR-E4)

For Talha (chat screens) and Sarim (QA cases). Text messages between a Guardian and a linked Dependent.

## The idea in 7 lines
1. A Guardian writes to a linked Dependent, and a Dependent writes to a linked Guardian. Guardian to Guardian, and Dependent to Dependent, are refused (`403 NOT_LINKED_TO_DEPENDENT`).
2. The **Primary** Guardian can always talk. A **Secondary** needs the `communication` permission from the Primary. The same check works in both directions and also for reading history. If the Primary takes it away, the Secondary cannot send, receive or read, and the conversation disappears from their list.
3. Each Guardian has **their own thread** with the Dependent (a message to the Primary is not shown to the Secondary).
4. Text is 1 to 2000 characters. Spaces at both ends are removed. An empty text is `422 VALIDATION_ERROR`.
5. Every message creates a **standard** notification (`type` = `message`) for the receiver, with the sender's name as title and the first 80 characters as body. `data.message_id` and `data.from_user_id` are included. If the push fails, the message is still saved.
6. **Safe retry:** the app makes a new random `client_id` for each message. If the network fails and the app sends the same message again with the same `client_id`, the server does NOT send twice: it answers `200` with the first message and `already_sent: true`. Same `client_id` with a different text or receiver is `409 CLIENT_ID_REUSED`.
7. **Read receipts:** `POST /messages/read` marks everything the other person sent as read. The sender then sees `read_at` on their messages.

## POST `/messages`
Body: `{ "receiver_id": "<user id>", "body": "Did you eat?", "client_id": "<uuid, optional>" }`
Reply `201` (first time) or `200` (repeat with the same `client_id`):
`{ message_id, sender_id, receiver_id, type: "text", body, content_url: null, priority: "standard", sent_at, read_at: null, from_me: true, already_sent: false }`

## GET `/messages?with_user_id=<id>&limit=30&before=<datetime>`
Newest first. `limit` 1 to 100 (default 30). If `next_before` is not null, pass it as `before` to load older messages. Reply: `{ items: [ ...message ], next_before }`. `from_me` tells which side to draw.

## GET `/messages/conversations`
All my conversations, most recent first: `{ items: [ { user_id, name, role, last_message, unread_count } ], total_unread }`. Use `total_unread` for the badge.

## POST `/messages/read`
Body: `{ "with_user_id": "<id>" }`. Reply: `{ "marked_read": 2 }`. Safe to repeat (second time gives 0).

## Errors
| Code | Status | When |
|---|---|---|
| `NOT_AUTHENTICATED` | 401 | no / bad token |
| `NOT_LINKED_TO_DEPENDENT` | 403 | not linked, unknown user, same role, or yourself |
| `MODULE_ACCESS_DENIED` | 403 | Secondary without `communication` (details: `module`) |
| `GUARDIAN_NOT_VERIFIED` | 403 | the Guardian side has not verified phone or CNIC |
| `CLIENT_ID_REUSED` | 409 | same `client_id`, different message |
| `VALIDATION_ERROR` | 422 | empty / too long text, bad id, bad `limit` |

## Priority voice messages (Task 4.3, FR-E4)
One-way urgent audio from a **Guardian** to a linked Dependent. Same rules as text (linked, Primary always, Secondary needs `communication`, each Guardian has their own thread). A Dependent cannot send one (`403 FORBIDDEN`).

* The message is always **critical**: the receiver gets a critical `voice_message` notification (`data.message_id`, `data.from_user_id`, `data.duration_s`) and a high-priority push. It can be acknowledged like any critical notification (`POST /notifications/{id}/acknowledge`).
* It shows in `GET /messages` and `GET /messages/conversations` like text: `type` = `priority_voice`, `body` = null, `duration_s`, and `content_url` = `/messages/{message_id}/audio`. Read receipts (`POST /messages/read`) work the same.

### POST `/messages/voice`  (multipart form, not JSON)
| Field | Rule |
|---|---|
| `receiver_id` | the linked Dependent |
| `duration_s` | 1 to 120 (the app sends the length it recorded) |
| `audio` | the recorded file, up to 2 MB: m4a/aac, mp3, ogg, webm, wav or amr. The server checks the real file header, not the name or `Content-Type` |
| `client_id` | optional, same safe-retry rule as text (retry = `200` + `already_sent`, no second file, no second notification) |

Reply `201`: the message (`type: "priority_voice"`, `priority: "critical"`, `duration_s`, `content_url`).

### GET `/messages/{message_id}/audio`
The audio bytes. Needs the login token (send the header; a plain audio player URL will not work, download first or use a player that sets headers). Only the sender and the receiver, and only while they may still talk (a Secondary who loses `communication` can no longer download).

### Voice errors
| Code | Status | When |
|---|---|---|
| `FORBIDDEN` | 403 | a Dependent tries to send |
| `UNSUPPORTED_AUDIO` | 415 | not a supported audio file |
| `AUDIO_TOO_LARGE` | 413 | over 2 MB |
| `VALIDATION_ERROR` | 422 | no audio part, empty file, `duration_s` outside 1 to 120 |
| `MESSAGE_NOT_FOUND` | 404 | unknown id, a text message, or not your message |
| `AUDIO_NOT_FOUND` | 404 | the file is gone from the server |
Plus the text errors above (`MODULE_ACCESS_DENIED`, `CLIENT_ID_REUSED`, ...).

Where files live: server setting `VOICE_STORAGE_DIR` (default `~/humsafar_uploads/voice`, outside the repo). Moving to a cloud bucket later is one new class in `storage_service.py`; the API does not change.

## Not in this task
Calls are Task 4.4.
