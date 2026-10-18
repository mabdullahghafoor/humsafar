# External Emergency Contact contract (Task 3.8, FR-R1)

For Talha (settings screen for the contact) and Sarim (QA cases).

## The idea in 6 lines
1. Each Dependent has **ONE** external emergency contact: a person outside the app (name + phone), for example a relative.
2. Only the **Primary Guardian** sets, replaces or removes it. A Secondary with the `emergency_alerts` permission can only **read** it. The Dependent cannot read it (it is another person's phone number).
3. When an alert (panic, missed dose, wellness check) is **not opened** by any Guardian, the escalation chain moves it to the last level, `external_contact` (see `escalation_contract.md`).
4. The server then sends **one SMS** to the contact. A mock gateway is used for now (`SMS_PROVIDER=mock`); a real gateway is one new class later.
5. The **Primary Guardian is told** in the app: "Emergency contact messaged" (standard), or, if there is no contact or the SMS failed, a **critical** notification.
6. When the alert is closed, the contact gets one short "all clear" SMS.

## PUT `/dependents/{id}/emergency-contact`
Primary Guardian only (verified). Sets the contact, or replaces it (still one row; `contact_id` does not change).
```json
{ "name": "Aunt Sara", "phone": "0300 1234567" }
```
Phone: `03XXXXXXXXX`, `+923XXXXXXXXX`, `923...`, `00923...` or another international number. It is saved as `+923001234567`.
Reply `200`: `{ "contact_id": "uuid", "name": "Aunt Sara", "phone": "+923001234567" }`.
Errors: `422 VALIDATION_ERROR` (bad name or phone), `403 NOT_PRIMARY_GUARDIAN` (a Secondary), `403 NOT_LINKED_TO_DEPENDENT`, `403 FORBIDDEN` (a Dependent), `403 GUARDIAN_NOT_VERIFIED`, `401 NOT_AUTHENTICATED`.

## GET `/dependents/{id}/emergency-contact`
The Primary, or a Secondary with `emergency_alerts`. Reply as above. `404 EMERGENCY_CONTACT_NOT_FOUND` if none is set. A Secondary without the permission gets `403 MODULE_ACCESS_DENIED`; a Dependent gets `403 FORBIDDEN`.

## DELETE `/dependents/{id}/emergency-contact`
Primary only. `204`, also when there was nothing to remove.

## When the SMS is sent
| Situation | What happens |
|---|---|
| Alert reaches `external_contact` and a contact exists | One SMS, within about a minute (the job runs every minute). Primary gets "Emergency contact messaged". |
| No contact is set | Primary gets ONE critical "No emergency contact set". If a contact is added later while the alert is still open, the SMS goes out on the next run. |
| Gateway is down | Retried every `SMS_RETRY_S` (60 s), up to `SMS_MAX_ATTEMPTS` (3). Then the Primary gets a critical "Emergency contact could not be reached". |
| Alert closes before the SMS | Nothing is sent. |
| Alert closes after the SMS | One all-clear SMS to the contact. |
Never two alert SMS for the same alert, even with several server processes.

## What the SMS says
* Panic: `HUMSAFAR URGENT: <name> pressed the panic button and needs help now. Please call <primary phone>. Hello <contact>, please check on them.`
* Missed dose / wellness check: `HUMSAFAR: <name> has <missed a medicine dose | not answered a wellness check>, and their family has not answered. Please call <primary phone>. Hello <contact>, please check on them.`
* All clear: `HUMSAFAR: The alert for <name> is closed. No action is needed. Thank you.`

## What the Primary's app receives
| type | priority | `data.result` | title |
|---|---|---|---|
| `external_contact` | standard | `sent` | Emergency contact messaged |
| `external_contact` | critical | `no_contact` | No emergency contact set |
| `external_contact` | critical | `failed` | Emergency contact could not be reached |
All have `data.event_id` and `data.dependent_id`.

## Trying it by hand
Set the contact as the Primary. Press panic as the Dependent. Wait 5 minutes (or set `ESCALATION_PRIMARY_TIMEOUT_S=10` in `.env`). The server log shows `MOCK SMS -> +92...`.
