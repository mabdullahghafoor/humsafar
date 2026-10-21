# Linkage API Contract (Task 1.5)

Status: implemented on branch `feature/1.5-linkage-endpoints`. Owner: Abdullah (backend). Consumers: Talha (linking and invite screens), Sarim (QA).
Errors use the standard envelope from `auth_contract.md` section 1. Branch on `error.code`.

## 1. Rules (SRS FR-B1, B2, B4, FR-A1)
- A Dependent needs exactly **one Primary Guardian**; plus up to **two Secondary** (maximum 3 Guardians).
- Only a **Primary-designated** Guardian links a Dependent. A Guardian who registers normally is Primary.
- A **Secondary** account exists only through an **invitation** from a Dependent's Primary. Designation is fixed per account (FR-A1): a Primary account cannot accept a Secondary invitation.
- One Guardian can be linked to **many** Dependents.
- Linking and inviting need a **verified** Guardian (see `kyc_contract.md`), otherwise 403 `GUARDIAN_NOT_VERIFIED`.
- A Dependent becomes active (can log in) once KYC is `verified` **and** a Primary is linked. Linking does not need KYC to be done first; the order does not matter.

All endpoints need `Authorization: Bearer <access_token>`.

## 2. Endpoints

### POST /dependents/{id}/link → 201
A verified Primary Guardian links themselves to the Dependent `{id}` (the Dependent's `user_id`). No body.
```json
{ "link_id": "uuid", "dependent_id": "uuid", "guardian_id": "uuid", "role": "primary", "status": "active", "linked_at": "..." }
```
Errors: 403 `GUARDIAN_NOT_VERIFIED`, 403 `SECONDARY_CANNOT_LINK`, 403 `FORBIDDEN` (not a Guardian), 404 `DEPENDENT_NOT_FOUND`, 409 `ALREADY_LINKED`, 409 `PRIMARY_ALREADY_EXISTS`, 409 `GUARDIAN_CAP_REACHED`.

### POST /dependents/{id}/guardians/invite → 200
The Dependent's Primary invites a Secondary by phone number. Body `{ "phone": "03001234567" }`.
```json
{ "invite_token": "<signed token>", "invited_phone": "+923001234567", "expires_at": "...", "expires_in": 604800 }
```
The app shares `invite_token` with the invitee (WhatsApp, SMS, etc.). It is valid for **7 days** and works **only for the invited phone number**.
Errors: 403 `GUARDIAN_NOT_VERIFIED`, 403 `NOT_PRIMARY_GUARDIAN` (not this Dependent's Primary), 409 `GUARDIAN_CAP_REACHED`, 409 `INVITEE_NOT_ELIGIBLE` (one generic answer for: a Primary-designated account, a Dependent's phone, or someone already linked, so the endpoint cannot be used to discover who has an account), 422 `VALIDATION_ERROR`.

### Accepting an invitation — two paths
1. **New person:** `POST /auth/register` with the usual fields **plus** `"invite_token": "..."` and the **invited phone number**. The account is created as `guardian_role: "secondary"` and linked in one step. If anything fails (including a full cap) no account is created.
   Errors: 400 `INVITE_INVALID`, 400 `INVITE_EXPIRED`, 403 `INVITE_NOT_FOR_YOU` (phone differs), 409 `GUARDIAN_CAP_REACHED`, 422 (`invite_token` with role `dependent`).
2. **Existing Secondary account** (to join another Dependent): `POST /invitations/accept` with `{ "invite_token": "..." }` → 201, same body as link, `role: "secondary"`.
   Errors: 400 `INVITE_INVALID` / `INVITE_EXPIRED`, 403 `PRIMARY_CANNOT_ACCEPT_INVITE`, 403 `INVITE_NOT_FOR_YOU`, 409 `ALREADY_LINKED`, 409 `GUARDIAN_CAP_REACHED`.

### GET /guardians/me/dependents → 200
Every Dependent this Guardian is linked to (FR-B4 "switch between Dependents"):
```json
[ { "dependent_id": "uuid", "email": "...", "phone": "+92...", "my_role": "primary",
    "kyc_status": "verified", "account_active": true, "linked_at": "..." } ]
```
`kyc_status`: `pending` | `verified` | `failed`. There is no name field (see `../backend/sds_clarifications.md`).

### GET /dependents/{id}/guardians → 200
Everyone linked to this Dependent, Primary first. Only Guardians linked to that Dependent may call it (else 403 `NOT_LINKED_TO_DEPENDENT`).
```json
[ { "guardian_id": "uuid", "email": "...", "phone": "+92...", "guardian_role": "primary", "verified": true, "linked_at": "..." } ]
```

## 3. How the Dependent's ID reaches the Guardian
The SDS does not say. The Dependent receives their `user_id` from `/auth/register`; the Dependent app should show it (text or QR) so the Primary can enter or scan it. Talha: please plan this screen. See the open security note in `../backend/sds_clarifications.md` (item 9).

## 4. Typical demo flow (ICP-1)
1. Guardian registers, logs in, verifies (CNIC or OTP).
2. Dependent registers, submits KYC.
3. Guardian calls `POST /dependents/{id}/link` → the Dependent can now log in.
4. Guardian invites a Secondary by phone; the invitee registers with the token.
5. (Task 1.6) The Primary configures what the Secondary may see.

## 5. Added or deviating (flagged)
- `GET` listings, `POST /invitations/accept` and the `invite_token` field on `/auth/register` are additions (the SDS lists only link and invite).
- The SDS has no invitations table; invitations are signed, expiring tokens (stateless). They cannot be individually revoked before they expire.
- Linking and inviting require a verified Guardian (the SRS actors table defines the Primary as "registered, verified").
- There is no unlink/remove endpoint yet; the SRS does not specify one.
