# Panic Mode contract (Task 3.6, FR-D2)

For Talha (Panic Mode screen 3.11, Guardian alert screens) and Sarim (mockups, QA cases).

## The idea in 6 lines
1. The **Dependent** presses one big button: `POST /dependents/{id}/panic`. No body, no extra check.
2. The server tells **every linked Guardian** (Primary and all Secondaries) at once with a **critical** notification, `type: "panic"`, title "PANIC ALERT". **Permissions do not matter.** This is the one deliberate exception to the permission model.
3. Only one panic is open at a time. Pressing again changes nothing (`already_active: true`), so a double tap is safe.
4. If no Guardian opens the alert in time, the escalation chain (see `escalation_contract.md`) moves it to the external-contact level. Opening it (`POST /escalations/{event_id}/acknowledge`) stops that.
5. It ends when the **Dependent** says "I am safe" or the **Primary Guardian** closes it: `POST /dependents/{id}/panic/resolve`.
6. When it ends, everyone who was told gets a standard all-clear ("Panic alert closed").

## POST `/dependents/{id}/panic`
Dependent only, and only for themself (`403 FORBIDDEN` otherwise). No body.
`201` the first time, `200` if a panic was already open.
```json
{ "event_id": "uuid", "status": "open", "tier": "primary", "triggered_at": "2026-10-18T03:00:00Z",
  "acknowledged_at": null, "resolved_at": null, "notified": 2, "already_active": false }
```
`notified` = how many Guardians were told. `tier` becomes `external_contact` if nobody opens the alert in time.

## GET `/dependents/{id}/panic`
The Dependent, or any linked Guardian (no module permission needed). Reply:
```json
{ "active": true, "panic": { "...same fields as above..." } }
```
`{ "active": false, "panic": null }` when nothing is open. `403 NOT_LINKED_TO_DEPENDENT` for a Guardian who is not linked.

## POST `/dependents/{id}/panic/resolve`
The Dependent, or the Primary Guardian. A Secondary gets `403 NOT_PRIMARY_GUARDIAN`. `409 NO_ACTIVE_PANIC` if nothing is open. Reply: the panic with `status: "resolved"` and `resolved_at`.

## What the Guardian sees
A critical notification: title "PANIC ALERT", body "{name} pressed the panic button and needs help now.", `data.event_id`, `data.tier`. The location is NOT included; the Guardian reads it from the location endpoints (which still need `live_location` for a Secondary).

## Trying it by hand
Log in as the Dependent, `POST /dependents/{id}/panic`, then look at `GET /notifications` as the Primary and as a Secondary with no grants. Both show the alert.
