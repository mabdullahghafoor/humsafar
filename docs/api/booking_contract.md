# Home-care booking requests and Activity Timeline contract (Task 6.2, FR-J1 and FR-I2/J2)

For Talha (directory and marketplace screens, task 6.8) and Sarim (mockups 18c "Request a visit" and 18d "Activity log", QA 6.12). Providers and organizations come from `directory_contract.md` (6.1).

## The idea in 9 lines
1. **A request is a note of intent.** Providers have no accounts, so nothing is sent to them. The request is saved, the family sees it, and the app opens the phone dialer with the provider's `contact`.
2. **The family keeps the status:** `pending` -> `confirmed` -> `completed`, or `cancelled` (from pending or confirmed). Finished ones are final. No payment.
3. **Who may ask and read:** the Dependent (own), the Primary, a Secondary with `health_records` (same gate as appointments). **Who may change a status:** the person who asked, or the Primary.
4. **One open request per provider** for a Dependent (`409 BOOKING_ALREADY_OPEN`); at most 20 open at a time (`409 TOO_MANY_OPEN_BOOKINGS`).
5. **Safe retry:** send a random `client_id`. A retry returns the first request (`200`, `already_saved: true`). The same id for a different provider or Dependent is `409 CLIENT_ID_REUSED`.
6. **Quick contact log:** when the user taps Call on an organization, the app first calls `POST .../directory/contacts`, then opens the dialer. The same person and organization within 60 seconds is logged once (`200`).
7. **One Activity Timeline** per Dependent: every organization contact and every booking step (requested, confirmed, completed, cancelled), from everyone, newest first. Each entry says who did it and keeps the name as it was.
8. **Notifications:** a standard `booking_update` notice goes to the others involved (not the person who acted) when a request is made or its status changes. Contacts are not notified.
9. Nothing here is medical advice or a guarantee that a provider will come.

## Endpoints (`{id}` = the Dependent's user id)
| Method and path | Who | What |
|---|---|---|
| POST `/dependents/{id}/bookings` | Dependent, Primary, Secondary with `health_records` | Body `{ provider_id, preferred_at?, note?, client_id? }`. `preferred_at` has a time zone, is in the future, within 365 days. `note` up to 300 characters. `201` with the request, `200` on a retry |
| GET `/dependents/{id}/bookings` | same | Query `status` (pending / confirmed / completed / cancelled), `limit` (1-200, default 50), `offset`. Newest first. `{ items, total, limit, offset }` |
| GET `/dependents/{id}/bookings/{request_id}` | same | One request |
| POST `/dependents/{id}/bookings/{request_id}/confirm` | the person who asked, or the Primary | pending -> confirmed |
| POST `/dependents/{id}/bookings/{request_id}/complete` | same | confirmed -> completed |
| POST `/dependents/{id}/bookings/{request_id}/cancel` | same | pending or confirmed -> cancelled |
| POST `/dependents/{id}/directory/contacts` | Dependent, Primary, Secondary with `health_records` | Body `{ org_id }`. Logs the contact. `201` the entry, `200` if the same person logged the same organization in the last 60 seconds |
| GET `/dependents/{id}/activity` | same | Query `type`, `from`, `to` (with time zone), `limit` (1-200, default 50), `offset`. `{ items, total, limit, offset }` |

Booking fields: `request_id`, `dependent_id`, `provider_id`, `provider_name`, `specialization`, `contact`, `service_charge` (PKR, may be null), `charge_unit`, `status`, `requested_by`, `requested_by_name`, `requested_at`, `preferred_at`, `note`, `updated_at`, `already_saved`. The provider details are the provider's current ones.

Activity entry fields: `activity_id`, `dependent_id`, `type` (`org_contact`, `booking_request`, `booking_confirmed`, `booking_completed`, `booking_cancelled`), `occurred_at`, `initiated_by` `{ user_id, full_name, role }` (role: `dependent`, `primary`, `secondary`, `former_guardian`), `subject_name` (the organization or provider as named at that moment), `reference_id` (organization id for `org_contact`, request id for booking steps), `booking_status` (the request's status now; null for `org_contact`).

```json
POST /dependents/{id}/bookings
{ "provider_id": "...", "preferred_at": "2026-10-24T10:00:00+05:00", "note": "Injection every morning for 5 days", "client_id": "..." }
201 { "request_id": "...", "status": "pending", "provider_name": "Demo Nurse Ayesha", "contact": "0300-1000001",
      "service_charge": 2500.0, "charge_unit": "per_visit", "requested_by_name": "Ali", "already_saved": false, "...": "..." }
```

## Errors
| Status | Code | When |
|---|---|---|
| 401 | `NOT_AUTHENTICATED` | No token |
| 403 | `FORBIDDEN` | Not the person who asked and not the Primary (status change); a Dependent using another Dependent's id |
| 403 | `NOT_LINKED_TO_DEPENDENT`, `MODULE_ACCESS_DENIED`, `GUARDIAN_NOT_VERIFIED` | Guardian not linked / no `health_records` / not verified |
| 404 | `PROVIDER_NOT_FOUND` | Unknown or hidden provider |
| 404 | `BOOKING_NOT_FOUND` | Unknown request, or one that belongs to another Dependent |
| 404 | `NOT_FOUND` | Unknown or hidden organization (contacts) |
| 409 | `BOOKING_ALREADY_OPEN` | An open request to this provider already exists |
| 409 | `TOO_MANY_OPEN_BOOKINGS` | 20 open requests already |
| 409 | `BOOKING_STATUS_CONFLICT` | The status change is not allowed from the current status (`details.status`) |
| 409 | `CLIENT_ID_REUSED` | The `client_id` belongs to a different request |
| 422 | `VALIDATION_ERROR` | `preferred_at` in the past, over a year ahead or without a time zone; note over 300 characters or with a NUL character; bad ids, `type`, `status`, paging |

## Notes for the app
* After `POST .../bookings` succeeds, show the provider's `contact` with a Call button.
* Show `status` as a chip; the Primary or the person who asked gets the Confirm / Done / Cancel actions.
* Use `booking_status` on timeline entries to show the current state next to a "requested" line.
* `former_guardian` can appear on old entries after a Guardian was unlinked.
