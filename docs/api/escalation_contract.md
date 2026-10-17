# Escalation chain contract (Task 3.5, FR-D5)

For Talha (Guardian alert screens) and Sarim (test cases for the escalation chain).

## The idea in 6 lines
1. An alert that needs a person (missed dose, unanswered wellness check, panic) is an **event**. It starts at the **primary** level: the Primary Guardian gets a critical notification.
2. If the Primary does not **open** it within **5 minutes**, the server moves it to **secondary**: Secondary Guardians who have `emergency_alerts` get the same alert (`data.tier` = `secondary`).
3. If nobody opens it within 5 more minutes, it moves to **external_contact**. (Sending the SMS to the external contact is Task 3.8.)
4. "Open" means the Guardian tapped the notification (`POST /notifications/{id}/acknowledge`) or called `POST /escalations/{event_id}/acknowledge`. That **stops the chain**.
5. A level with nobody to tell is skipped. Panic tells all Guardians at once, so it goes straight to `external_contact`.
6. The event closes when the problem is solved (dose taken, "I am OK", ...). Everyone who was told gets a standard all-clear.

Geofence, battery and offline alerts do not climb the chain.
A Guardian can also push a missed-dose alert up by hand (`.../escalate`, see `medication_contract.md`); the Secondary 5-minute timer then starts from that moment.

## GET `/dependents/{id}/escalations`
Primary, or Secondary with `emergency_alerts`. Query: `status` (`open` or `resolved`), `limit` (1 to 200, default 50). Newest first.
```json
{ "primary_timeout_s": 300, "secondary_timeout_s": 300,
  "items": [ { "event_id": "uuid", "trigger_type": "missed_dose", "reference_id": "uuid", "tier": "primary", "status": "open",
    "created_at": "2026-10-18T03:00:00Z", "tier_changed_at": "2026-10-18T03:00:00Z",
    "acknowledged_at": null, "acknowledged_by": null, "resolved_at": null,
    "next_escalation_at": "2026-10-18T03:05:00Z" } ] }
```
`tier` is `primary`, `secondary` or `external_contact`. `next_escalation_at` is `null` when the chain has stopped (opened, closed, or at the last level). `reference_id` is the dose (`confirmation_id`) or the wellness check prompt (`response_id`).

## POST `/escalations/{event_id}/acknowledge`
A Guardian who was told says "I have seen it". Acknowledges all of the caller's own alerts of this event and stops the chain. Reply: the same event object as above. Safe to repeat (first time kept). `404 ESCALATION_NOT_FOUND` for an unknown event, or one the caller was never told about (including every Dependent).

## Trying it by hand
Start the server with short timers: `$env:ESCALATION_PRIMARY_TIMEOUT_S="60"; $env:ESCALATION_SECONDARY_TIMEOUT_S="60"; uvicorn app.main:app --reload`. Make a missed dose or wellness check alert (see their contracts). Do not open it: after about 1 minute the event shows `secondary`, after about 1 more minute `external_contact`. The job runs once a minute, so each step can take up to a minute extra.
