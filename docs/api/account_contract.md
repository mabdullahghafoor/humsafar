# Account closure contract (Task 6.7, FR-O1)

Data is kept while an account is active. After a closure it is deleted or anonymized by a background job after **60 days** (`RETENTION_DAYS`). Until then the account can be reopened.

## Endpoints
| Call | Who | Body | Result |
|---|---|---|---|
| `POST /account/close` | a Guardian (their own account) | `{password}` | 200 `{user_id, status:"closed", closed_at, delete_after}` |
| `POST /account/reopen` | public (the person cannot sign in) | `{email, password}` | 200 a normal token pair (same as `/auth/login`) |
| `POST /dependents/{id}/close` | the Dependent's Primary Guardian | `{password}` (the Primary's) | 200 `{..., status:"closed"}` |
| `POST /dependents/{id}/reopen` | the same Primary | `{password}` | 200 `{..., status:"reopened", delete_after:null}` |

## What happens
* **Guardian closes their account:** signed out everywhere at once; their links end (the Primary gets a `guardian_left` notice, standard); push tokens removed. A **Primary who still has an active Dependent cannot close**: `409 CLOSE_DEPENDENTS_FIRST` with `details.dependent_ids`. Show "Close the Dependent's account first" and offer that.
* **Primary closes a Dependent:** the Dependent is signed out and cannot sign in; every Guardian loses access (links are paused, not deleted); doctor links stop; open alerts are closed; Secondaries get a `dependent_closed` notice. A Dependent cannot close their own account.
* **Sign-in / refresh / any call with an old token** on a closed account: `403 ACCOUNT_CLOSED`. For sign-in, `details` = `{delete_after, role}` (only shown after the right password). Show "This account was closed. You can reopen it until <delete_after>" for a Guardian, "Ask the Primary Guardian to reopen it" for a Dependent.
* **After the period:** the Dependent's data is deleted and the identity anonymized; a Guardian's details are anonymized. This cannot be undone. See `docs/backend/data_retention.md`.

## Errors
`403 WRONG_PASSWORD` (the confirmation password is wrong; 8 wrong tries in 5 minutes → `429 TOO_MANY_REQUESTS`), `401 INVALID_CREDENTIALS` (reopen), `409 CLOSE_DEPENDENTS_FIRST`, `409 ALREADY_CLOSED`, `409 NOT_CLOSED`, `403 FORBIDDEN` (a Dependent trying to close a Guardian account or a Dependent; a Guardian trying to reopen a Dependent's account by e-mail), `403 NOT_PRIMARY_GUARDIAN`, `403 NOT_LINKED_TO_DEPENDENT`, `403 GUARDIAN_NOT_VERIFIED`, `403 ACCOUNT_CLOSED`, `401 NOT_AUTHENTICATED`.
