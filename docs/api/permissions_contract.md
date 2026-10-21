# Permissions API Contract (Task 1.6)

Status: implemented on branch `feature/1.6-permission-endpoints`. Owner: Abdullah (backend). Consumers: Talha (Permission Management screen), Sarim (QA).
Errors use the standard envelope from `auth_contract.md` section 1. Branch on `error.code`. All endpoints need `Authorization: Bearer <access_token>`.

## 1. Rules (SRS FR-A4, FR-B4)
- Only the Dependent's **Primary Guardian** can grant or revoke. They do it **per module, per Secondary Guardian**.
- **Default deny:** a Secondary has no access to any module until the Primary grants it.
- A **Primary** always has every module. **Remote Alarm Override is not a module**: it is Primary-only and can never be granted (FR-A4.3, FR-D3).
- Permissions are **separate for each Dependent** (FR-B4). The same Secondary can have different access on two Dependents.
- A revoke takes effect on the **very next API call**. The permission is not stored in the token, so the app need not log out or refresh.
- Every grant or revoke is written to the audit log (FR-N3).

## 2. Modules (`module` values, exact spelling)
`live_location`, `health_records`, `communication`, `emergency_alerts`, `camera_viewing`, `medication_management`

The SRS says "at minimum", so the list may grow. The dashboard response always carries the current list in `modules`; build the screen from that list rather than hard-coding it.

## 3. Endpoints

### GET /dependents/{id}/permissions → 200 (Primary only, verified)
The dashboard: every Secondary and every module.
```json
{ "dependent_id": "uuid",
  "modules": ["live_location", "health_records", "communication", "emergency_alerts", "camera_viewing", "medication_management"],
  "secondaries": [ { "guardian_id": "uuid", "email": "...", "phone": "+92...",
                     "modules": { "live_location": false, "health_records": false, "...": false } } ] }
```
Errors: 403 `GUARDIAN_NOT_VERIFIED`, 403 `NOT_PRIMARY_GUARDIAN`.

### PUT /dependents/{id}/permissions/{module} → 200 (Primary only, verified)
Body: `{ "guardian_id": "uuid-of-the-secondary", "granted": true }`
```json
{ "dependent_id": "uuid", "guardian_id": "uuid", "module": "live_location", "granted": true, "updated_at": "..." }
```
Sending the same value again is harmless. Errors: 403 `GUARDIAN_NOT_VERIFIED`, 403 `NOT_PRIMARY_GUARDIAN`, 404 `SECONDARY_NOT_FOUND` (that Guardian is not linked to this Dependent), 400 `PRIMARY_NOT_GOVERNABLE` (you cannot restrict the Primary), 422 `UNKNOWN_MODULE` (`details.allowed` lists the valid names; this includes `remote_alarm`), 422 `VALIDATION_ERROR`.

### GET /dependents/{id}/permissions/me → 200 (any linked Guardian)
What the logged-in Guardian may do for this Dependent. Use it to show or hide screens.
```json
{ "dependent_id": "uuid", "guardian_role": "secondary", "modules": { "live_location": true, "camera_viewing": false, "...": false } }
```
A Primary gets `true` for every module. Errors: 403 `NOT_LINKED_TO_DEPENDENT`.

## 4. For every later feature (location, records, camera, ...)
A Secondary calling a data endpoint without a grant gets:
`403 { "error": { "code": "MODULE_ACCESS_DENIED", "details": { "module": "live_location" } } }`
Treat it as "hide or lock this feature", not as an error screen. An unverified Guardian gets 403 `GUARDIAN_NOT_VERIFIED`. The backend enforces this with one shared check, `require_module_access("<module>")`, so no feature can forget it.

## 5. Added or deviating (flagged)
- The SDS gives `PUT /dependents/{id}/permissions/{module}` but no way to say **which** Secondary. We pass `guardian_id` in the body.
- The two `GET` endpoints are additions (the dashboard needs a read).
- A Secondary must also be verified (phone OTP or CNIC) before any granted module works (FR-A3). Verification is per account, done once.
- `audit_logs` has no detail columns (SDS 9.2), so each entry stores who acted, `permission_granted` / `permission_revoked`, and the grant row's id. The module and Secondary are found through that grant row.
