# Geofence API contract (Task 2.2, FR-C2 / FR-C3)

For Talha (Task 2.6, Live Map and geofence screens). Same base URL and error envelope as the other contracts.

## Rules in plain words
* The **Primary Guardian** (verified) creates, changes and deletes safe zones. A Secondary can only **view** them, and only with the `live_location` permission. The Dependent cannot see or change zones.
* A zone is a circle: a centre (`lat`, `lng`) and `radius_m` (50 m to 50,000 m). Up to **10 zones** per Dependent.
* **Inside any zone = safe. Outside all zones = breach.** With no zones there is no breach.
* A breach is opened **once** when the Dependent goes from safe to outside, and closed when they are back inside (or the zones change so they are inside, or the zones are removed). More fixes while still outside do not create more breaches, so there is no alert spam.
* The newest location fix decides. A late, older fix cannot change the state.
* GPS error is allowed for: a fix counts as inside if it is within `radius_m + accuracy_m` (the allowance is capped at 100 m).
* Alerts to Guardians: the breach is recorded as an open `escalation_events` row (type `geofence_breach`). Sending the notification arrives with the notification service (Task 3.1). Until then, poll `geofence-status` to show a breach on screen.

## POST `/dependents/{id}/geofences`  (Primary only) -> 201
```json
{ "name": "Home", "lat": 24.8607, "lng": 67.0011, "radius_m": 300 }
```
Response: `{ "geofence_id", "dependent_id", "name", "lat", "lng", "radius_m", "created_by" }`.
Errors: `409 GEOFENCE_LIMIT_REACHED`, `403 NOT_PRIMARY_GUARDIAN` (Secondary, or not this Dependent's Primary), `403 GUARDIAN_NOT_VERIFIED`, `422 VALIDATION_ERROR`.

## GET `/dependents/{id}/geofences`  (Primary, or Secondary with `live_location`)
```json
{ "dependent_id": "...", "count": 2, "max_zones": 10, "geofences": [ { "geofence_id": "...", "name": "Home", "lat": 24.8607, "lng": 67.0011, "radius_m": 300.0, "dependent_id": "...", "created_by": "..." } ] }
```
Errors: `403 MODULE_ACCESS_DENIED`, `403 NOT_LINKED_TO_DEPENDENT`.

## PUT `/dependents/{id}/geofences/{geofence_id}`  (Primary only) -> 200
Same body as create; replaces the zone. Errors: `404 GEOFENCE_NOT_FOUND` (also when the zone belongs to another Dependent).

## DELETE `/dependents/{id}/geofences/{geofence_id}`  (Primary only) -> 204 (no body)

## GET `/dependents/{id}/geofence-status`  (Primary, or Secondary with `live_location`)
```json
{ "dependent_id": "...", "status": "outside", "inside_zone_ids": [], "breach_open": true, "breach_event_id": "...", "breach_since": "2026-10-16T09:30:00Z" }
```
`status`: `inside`, `outside`, `no_zones`, or `unknown` (no location yet, or the newest fix is older than 8 minutes).

## Also changed: the location reply (Task 2.1 endpoint)
`POST /dependents/{id}/location` now returns two more fields: `geofence_status` (`no_zones` | `inside` | `outside`) and `breach_started` (true only on the fix that opened a new breach). The Dependent's phone may use them (for example, a gentle "you left the safe area" message).

## When zones change
Adding, moving or deleting a zone re-checks the Dependent's newest known position straight away. If they are now outside all zones, a breach opens (only if the position is fresh, under 8 minutes old); if they are now inside, an open breach closes.
