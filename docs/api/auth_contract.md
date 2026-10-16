# Auth API Contract (Task 1.3)

Status: implemented on branch `feature/1.3-auth-endpoints`. Owner: Abdullah (backend). Consumer: Talha (Flutter, Task 2.5).
Base URL (local): `http://127.0.0.1:8000`. All bodies are JSON.

## 1. Error envelope (SDS 11.2) — every error, every endpoint

```json
{ "error": { "code": "MACHINE_READABLE_CODE", "message": "Human readable text", "details": {} } }
```

Branch on `error.code`, never on `message`.

## 2. Endpoints

### POST /auth/register  → 201
Request:
```json
{ "email": "ali@example.com", "phone": "03001234567", "password": "min-8-chars", "full_name": "Ali Khan", "role": "guardian" }
```
- `role`: `"guardian"` or `"dependent"` only.
- `email`: stored lower-case; unique case-insensitively.
- `phone`: any common Pakistani format (`03001234567`, `+92 300 1234567`) is normalised to E.164 (`+923001234567`); unique after normalisation.
- `password`: at least 8 characters, at most 72 bytes (bcrypt limit).
- A guardian registering independently is a **primary** guardian (FR-A1). `guardian_role` cannot be chosen by the client. Secondary guardians come only via invitation (Task 1.5).
- `invite_token` (optional, Guardians only, added in Task 1.5): registers the account as a **Secondary** Guardian linked to the inviting Dependent. See `linkage_contract.md`. Without it, a Guardian is Primary.
- `full_name` (required, added in Task 2.5 prep): 2 to 100 characters. Extra spaces are trimmed and collapsed. Returned in every `user` object (register, login, `/auth/me`).

Response 201:
```json
{ "user_id": "uuid", "email": "ali@example.com", "phone": "+923001234567", "full_name": "Ali Khan",
  "role": "guardian", "guardian_role": "primary", "created_at": "2026-10-13T23:54:10+05:00" }
```
`guardian_role` is `null` for dependents. Registration does **not** return tokens; call `/auth/login`.

Errors: 409 `EMAIL_ALREADY_REGISTERED`, 409 `PHONE_ALREADY_REGISTERED`, 409 `ALREADY_REGISTERED` (race), 422 `VALIDATION_ERROR`.

### POST /auth/login  → 200
Request: `{ "email": "...", "password": "..." }`

Response 200:
```json
{ "access_token": "jwt", "refresh_token": "jwt", "token_type": "bearer",
  "expires_in": 900, "user": { "user_id": "...", "email": "...", "phone": "...", "full_name": "...", "role": "...", "guardian_role": "...", "created_at": "..." } }
```
Errors:
- 401 `INVALID_CREDENTIALS` — wrong password OR unknown email (deliberately identical).
- 403 `ACCOUNT_NOT_ACTIVATED` — dependent who has not passed KYC liveness **and** been linked to an active Primary guardian (FR-A2). Only returned after a correct password. Show "waiting for your guardian / verification" screen.
- 422 `VALIDATION_ERROR`.

Guardians can log in right after registering. Feature gating by verification (FR-A3) comes with Task 1.4.

### POST /auth/refresh  → 200
Request: `{ "refresh_token": "jwt" }`. Response: same shape as login (a **new pair**; store the new refresh token and discard the old one).
Errors: 401 `TOKEN_EXPIRED` (send user to login), 401 `TOKEN_INVALID`, 401 `TOKEN_WRONG_TYPE` (an access token was sent), 403 `ACCOUNT_NOT_ACTIVATED`.

### GET /auth/me  → 200  (helper beyond the SDS list)
Header `Authorization: Bearer <access_token>`. Returns the user object above. Useful to restore the session on app start.
Errors: 401 `NOT_AUTHENTICATED` (no header), 401 `TOKEN_EXPIRED` (call `/auth/refresh`, retry once), 401 `TOKEN_INVALID`, 401 `TOKEN_WRONG_TYPE`.

## 3. Tokens
| | Access | Refresh |
|---|---|---|
| Lifetime | 15 minutes (`expires_in` = 900 s) | 7 days |
| Use | `Authorization: Bearer` on every protected call | only `/auth/refresh` |
| Claims | `sub` (user_id), `role`, `type`, `iat`, `exp`, `jti` | same |

Algorithm HS256. Tokens are stateless: there is no server-side revocation or logout in this release (client logout = delete tokens locally).

## 4. Suggested client flow (Flutter)
1. Store both tokens in secure storage.
2. On any 401 with `TOKEN_EXPIRED`: call `/auth/refresh` once, replace both tokens, retry the original request. If refresh fails → login screen.
3. On any other 401 → login screen.

## 5. Added beyond the SDS list (flagged)
- `POST /auth/refresh` and `GET /auth/me` (small, needed for the 15-minute access token and session restore).
- Error codes for token problems (`TOKEN_EXPIRED`, `TOKEN_INVALID`, `TOKEN_WRONG_TYPE`).
- Refresh rotation without revocation. Revocation and auth rate limiting are deferred to hardening (SDS 17).

## 6. Open decisions needing Talha + Abdullah
- ~~Does `users` get a `full_name` column?~~ Settled: yes (clarification item 27).
- `messages` has no text body column (affects Phase 4, not 1.3).
