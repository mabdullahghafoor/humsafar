# SDS Gaps and Clarifications

The SRS/SDS baselines are locked. This file records every place where implementation hit a gap or contradiction, what was done in the meantime, and what needs a team decision. Nothing here changes the locked documents; it is the paper trail.

| # | Found in | Issue | What we did | Needs decision |
|---|---|---|---|---|
| 1 | SDS 9.2 `users` | No name column, so the apps cannot store a person's name. | Task 1.3 register takes email, phone, password, role only. | Abdullah + Talha: add `full_name`? (Before the register screen is final.) |
| 2 | SDS 9.2 `messages` | No text body column (only `content_url`), but FR-E1 includes text messages. | Not needed until Phase 4. | Decide before Phase 4. |
| 3 | SDS 11.1 vs 11.3 | `POST /dependents/{id}/kyc-verify` is marked JWT, but 11.3 says Dependents get no token until KYC succeeds. | Endpoint kept as specified; the Dependent authenticates with their password in the body. | Confirm with the supervisor/team that this is acceptable. |
| 4 | SDS 11.3 vs FR-A3 | 11.3 says Guardian OTP happens before first token issuance; FR-A3 says verification must happen before the permission dashboard or interventions. | Followed FR-A3 (the requirement): Guardians can log in, and are blocked from gated features until verified (`GUARDIAN_NOT_VERIFIED`). | Confirm. |
| 5 | SDS 9.2 `guardian_profiles` | No CNIC column. | Only the pass/fail result (`cnic_verified`) is stored. | None. |
| 6 | SDS 11.1 | No refresh or "who am I" endpoint, no Guardian verification endpoints. | Added `/auth/refresh`, `/auth/me`, `/guardians/me/*`. | None, flagged for the record. |
| 7 | SDS 17 | Rate limiting on auth/KYC endpoints. | Not built yet. | Schedule in a hardening task. |
| 8 | SDS 9.2 (no invitations table) | FR-B1 and FR-A1 need pending invitations to people who have no account yet, but there is nowhere to store them. | Invitations are signed, expiring (7 day) tokens bound to the invited phone number; no table needed. They cannot be revoked individually. | Confirm, or add an `invitations` table. |
| 9 | SDS 11.1 `POST /dependents/{id}/link` | The SDS does not say how a Guardian finds a Dependent, and has no Dependent consent step. Anyone who is a verified Primary-designated Guardian and knows a Dependent's `user_id` can claim the Primary role if none exists yet. | Dependent shares their `user_id` (a UUID, hard to guess). **Security risk left open.** | Recommended: a Dependent confirmation step (or a one-time link code). Decide before the demo. |
| 10 | FR-A1 | "Registers by creating its first Dependent is Primary" vs our flow where Dependents register themselves. | A guardian who registers normally is Primary; Secondary only through an invitation. | None. |
| 11 | SRS 6.1 actors | Linking is not listed as gated by FR-A3. | Linking and inviting require a verified Guardian (the actors table says "verified"). | Confirm. |
| 12 | FR-B1/B2 | No way to remove a Guardian or change a Primary (the link `status` can be `revoked` but no flow is specified). A wrongly linked Primary cannot be removed. | Not built. | Specify before Phase 4 hardening. |
| 13 | SDS 11.1 `PUT /dependents/{id}/permissions/{module}` | The URL names the module but not which Secondary Guardian is being changed. | `guardian_id` is sent in the request body. Added `GET /dependents/{id}/permissions` and `GET .../permissions/me`. | Confirm. |
| 14 | FR-A3 vs FR-A4 | A Secondary joins through an invitation, unverified. FR-A3 gates "any intervention capability" but does not say whether a granted view-only module counts. | A Secondary must be verified before any granted module works, in addition to the grant. | Confirm. |
| 15 | SDS 9.2 `audit_logs` | No column for the module, the affected Secondary or the old/new value, so permission changes (FR-N3) cannot be described fully. | Each change logs actor, action and the grant row's id; the module and Secondary follow from that row. A first-time "revoke" and a repeat of the same value are not logged. | Add a `details` column if the audit screen needs more. |
| 16 | FR-A4.3 | "Emergency Alert Visibility" is a module in the list, but the escalation code that must obey it arrives in Phase 3. | The switch exists and is stored; the Phase 3 escalation code must call `require_module_access("emergency_alerts")` before notifying a Secondary. | Remember in Phase 3. |

