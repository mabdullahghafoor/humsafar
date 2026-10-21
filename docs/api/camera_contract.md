# Camera contract (Task 6.3, FR-K1)

The camera is a spare Android phone signed in as the **Dependent**, in "camera mode" (Task 6.10 builds the app side). Video goes through a hosted video room (same provider as calls); the server only decides who may join. All errors use the standard envelope.

## Flow
1. Camera phone (or Primary) pairs: `POST /dependents/{id}/camera`.
2. Camera phone calls `POST /dependents/{id}/camera/heartbeat` every `next_poll_s` seconds. It publishes video **only** while `should_publish` is true, using `join` (publisher token, `user_id` = `camera-<dependent id>`).
3. A Guardian opens the camera: `GET /dependents/{id}/camera/stream` returns `join` (viewer token). The app logs in to `join.room_id` with `join.user_id` and plays `join.stream_id`. Call the same endpoint again every `renew_every_s` (30 s) to keep watching; `DELETE` to stop.
4. The Dependent's app polls `GET /dependents/{id}/camera/viewing` to show who is watching, and gets a `camera_view` notification.

## Endpoints
| Call | Who | Result |
|---|---|---|
| `POST /dependents/{id}/camera` body `{name?}` (max 60) | Dependent, Primary | 201 new / 200 renamed. `CameraStatus` |
| `GET /dependents/{id}/camera` | Dependent, Primary, Secondary with `camera_viewing` | `{paired, camera_id, name, paired_at, online, last_seen_at, viewers_now, max_viewers}` |
| `DELETE /dependents/{id}/camera` | Dependent, Primary | 204, ends every viewing; safe to repeat |
| `POST /dependents/{id}/camera/heartbeat` | the Dependent only | `{should_publish, viewers_now, next_poll_s, join?, clip?}` (10 s idle, 5 s while watched or while a `clip` task waits) |
| `GET /dependents/{id}/camera/stream` | Primary; Secondary with `camera_viewing` | `{session_id, camera_name, started_at, expires_at (90 s), renew_every_s, join{provider, app_id, room_id, stream_id, user_id, token, expires_at}, renewed}` |
| `DELETE /dependents/{id}/camera/stream` | anyone linked | 204, ends my own viewing; safe to repeat |
| `GET /dependents/{id}/camera/viewing` | the Dependent only | `{being_viewed, viewers[{user_id, full_name, role, since}]}` |

## Errors
`403 MODULE_ACCESS_DENIED` (Secondary without `camera_viewing`), `403 FORBIDDEN` (Dependent watching, Guardian sending heartbeat, Secondary pairing), `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`, `409 NO_CAMERA`, `409 CAMERA_OFFLINE` (`details.last_seen_at`), `409 TOO_MANY_VIEWERS` (3), `503 STREAM_PROVIDER_UNAVAILABLE`, `422 VALIDATION_ERROR`, `401 NOT_AUTHENTICATED`.

Responses with tokens carry `Cache-Control: private, no-store`. A viewer who loses `camera_viewing` is cut off at the next renewal at the latest.

## Emergency clips (Task 6.4, FR-K2)
When Panic Mode (3.6) or the Remote Alarm (3.7) starts and a camera is paired, a clip request is saved. The server cannot record a hosted video room, so the camera phone records.

1. The next heartbeat carries `clip: {clip_id, trigger_type (panic|remote_alarm), duration_s (20), requested_at, expires_at (+3 min)}`. The phone records `duration_s` seconds right away, **whatever `should_publish` says**.
2. `POST /dependents/{id}/camera/clips/{clip_id}`: multipart form, one field `file` (MP4 or WebM, up to 30 MB). Only the Dependent's own phone. 201 with the clip; stored encrypted (FR-N2). Primary and Secondaries with `camera_viewing` get a standard `camera_clip` notification.
3. A request not fulfilled before `expires_at` becomes `missed` (visible in the list). Unpairing also marks open requests `missed`.

| Call | Who | Result |
|---|---|---|
| `GET /dependents/{id}/camera/clips?status=&limit=&offset=` | Dependent, Primary, Secondary with `camera_viewing` | `{items[{clip_id, trigger_type, status (requested|stored|missed), event_id, captured_at, duration_s, uploaded_at, size_bytes, content_type}], total, limit, offset}` newest first |
| `GET .../clips/{clip_id}` | same | one clip |
| `GET .../clips/{clip_id}/video` | same | the video file (`Content-Disposition: attachment`). A Guardian's download is written to the audit log (`camera_clip_viewed`) |
| `DELETE .../clips/{clip_id}` | Dependent, Primary | 204, removes file and entry; safe to repeat |

Errors: `403 FORBIDDEN` (not the Dependent's phone), `403 MODULE_ACCESS_DENIED` / `NOT_PRIMARY_GUARDIAN`, `404 CLIP_NOT_FOUND`, `409 CLIP_ALREADY_STORED`, `409 CLIP_EXPIRED`, `413 FILE_TOO_LARGE`, `415 UNSUPPORTED_FILE`, `422 VALIDATION_ERROR`.
Audit actions: `camera_clip_stored`, `camera_clip_viewed`, `camera_clip_deleted`.
