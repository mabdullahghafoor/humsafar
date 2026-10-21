# Healthcare directory and home-care provider directory contract (Task 6.1, FR-I1 and FR-J1)

For Talha (directory and marketplace screens, task 6.8) and Sarim (QA, mockups 6.11). Booking a provider and the activity log come in Task 6.2; this contract is the **read side**.

## The idea in 8 lines
1. **Two lists:** healthcare organizations (hospitals, clinics, pharmacies, ambulances, emergency lines, blood banks, laboratories) and home-care providers (nurses, physiotherapists, attendants, home doctors, lab technicians).
2. **Read only.** The platform keeps the content; nobody edits it from the app. Providers have no accounts and never log in (FR-J1).
3. **Any signed-in user** may read it: Guardian (verified or not), Secondary, Dependent. It holds no personal data.
4. **Quick contact:** every entry has a `phone` (organizations) or `contact` (providers). The app opens the phone dialer; the server does not place calls. (The "contact was made" log entry is Task 6.2.)
5. **Nearby:** send `lat` + `lng` (the position of whoever is searching). Entries with a position get `distance_km` and come nearest first. **National numbers have no position** (Edhi 115, Chhipa 1020 ...): they always stay in the list, after the located ones, with `distance_km: null`, because they work everywhere.
6. **Demo entries:** `is_sample: true` means a made-up entry (made-up name and number). Only the six national emergency numbers are real for now. Show a small "sample" label in the app, and do not let the demo dial a sample number as if real. Real entries will replace them before the final demo (clarification 121).
7. **Search words** match name, city, address, services and type (organizations) / name, specialization, city and profile (providers), not case sensitive. A typed `%` or `_` is just a letter.
8. **Paging:** `limit` 1 to 100 (default 20), `offset`; the reply has `total` (the full count for the filters).

## Organizations
| Method and path | What |
|---|---|
| GET `/directory/organizations` | List. Query (all optional): `q`, `type`, `city`, `open_24h` (true/false), `lat` + `lng` (together), `radius_km` (needs lat + lng; national numbers are kept), `limit`, `offset`. Without a position the order is by name |
| GET `/directory/organizations/types` | `{ types: [ { type, count } ] }` for filter chips |
| GET `/directory/organizations/{org_id}` | One organization. `404 NOT_FOUND` if unknown or hidden |

`type` is one of `hospital`, `clinic`, `pharmacy`, `ambulance`, `emergency_service`, `blood_bank`, `laboratory`.

Organization fields: `org_id`, `name`, `type`, `phone` (may be null), `lat`, `lng` (null for national numbers), `address`, `city` (`"Nationwide"` for national numbers), `services` (short text), `open_24h`, `is_sample`, `distance_km` (null unless lat + lng were sent and the entry has a position).

```json
GET /directory/organizations?lat=31.55&lng=74.34&type=hospital&limit=2
{
  "items": [
    { "org_id": "...", "name": "Demo City General Hospital", "type": "hospital", "phone": "0300-0000001",
      "lat": 31.5497, "lng": 74.3436, "address": "Mall Road (demo address)", "city": "Lahore",
      "services": "Emergency, general medicine, surgery, pharmacy", "open_24h": true, "is_sample": true, "distance_km": 0.04 }
  ],
  "total": 1, "limit": 2, "offset": 0
}
```

## Providers
| Method and path | What |
|---|---|
| GET `/directory/providers` | List. Query (optional): `q`, `specialization` (exact, not case sensitive), `city`, `min_charge`, `max_charge`, `sort` = `name` (default) / `charge_asc` / `charge_desc` / `experience`, `limit`, `offset`. Unknown charge and unknown experience sort last |
| GET `/directory/providers/specializations` | `{ specializations: [ { specialization, count } ] }` |
| GET `/directory/providers/{provider_id}` | One provider. `404 NOT_FOUND` if unknown or hidden |

Provider fields: `provider_id`, `name`, `specialization` (`nurse`, `physiotherapist`, `attendant`, `doctor`, `lab_technician` today; read it from `/specializations`, do not hard-code), `service_charge` (a number in PKR, or null = ask the provider), `charge_unit` (`per_visit`, `per_hour`, `per_day`, `per_month`), `contact`, `bio`, `city`, `experience_years`, `is_sample`.

## Errors
| Status | Code | When |
|---|---|---|
| 401 | `NOT_AUTHENTICATED` | No token |
| 404 | `NOT_FOUND` | Unknown or hidden organization / provider |
| 422 | `VALIDATION_ERROR` | `lat` without `lng` (or the reverse), `radius_km` without a position, `lat` outside -90..90, `lng` outside -180..180, `radius_km` <= 0, unknown `type` or `sort`, `limit` outside 1..100, negative `offset` or charge, `min_charge` above `max_charge`, search words longer than 100 characters, bad id |

## Notes for the app
* Send the position only when the user allows location; without it the list is by name and `distance_km` is null.
* Show `distance_km` rounded (for example "2.4 km").
* A call button on a null `phone` should be hidden.
* The Dependent Mode quick contact list can call `GET /directory/organizations?type=ambulance` (national numbers, no position needed).
