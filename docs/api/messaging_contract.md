# Messaging contract (Task 4.2, FR-E1)

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

## Not in this task
Voice messages (4.3) use the same table and the same endpoints for history and read receipts: `type` = `priority_voice` and `content_url` instead of `body`. Calls are 4.4.
