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
