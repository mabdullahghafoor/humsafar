# Medical Vault contract (Task 5.1, FR-G1 and FR-G3)

For Talha (records screens, task 5.6) and Sarim (QA cases, 5.10). Store prescriptions, lab reports, X-rays and other records for a Dependent, export them as PDF, and give a doctor a read-only link.

## The idea in 9 lines
1. A record has a **category** (`prescription`, `lab_report`, `xray`, `other`), a **title**, a **record date** (the date of the document or visit), and a **file** (PDF, JPEG or PNG, up to 10 MB), a **note**, or both. A record with neither is refused (`422 RECORD_NEEDS_CONTENT`).
2. **Who can use the vault:** the Dependent for their own records; the **Primary** Guardian always; a **Secondary** only with the `health_records` permission (same check on every endpoint, so removing it works on the next request). Others get `403`.
3. **Who can change or delete a record:** the person who added it, or the Primary Guardian. The reply has `can_modify` so the screen can show or hide the buttons.
4. Files are checked by their **first bytes**, never by the name the phone sends (`415 UNSUPPORTED_FILE` for anything else). The stored name is cleaned. Files are **stored encrypted** on the server (AES-256-GCM, FR-N2); the app always gets the original file back.
5. **Safe retry:** send a new random `client_id` with each upload. If the network fails and the app sends it again, nothing is saved twice: `200` and `already_saved: true`. The same `client_id` with a different record is `409 CLIENT_ID_REUSED`.
6. A vault holds at most **500** records (`409 RECORDS_LIMIT`).
7. Reading a file, exporting, and every add / change / delete are written to the **audit log** (FR-N3).
8. The **PDF export** can be complete, one year, or one month (by record date). The **doctor link** opens the same PDF with no login and stops working after 72 hours (or when cancelled).
9. Task 5.2 will let the Primary hide record **categories** from a Secondary. Nothing changes for the app now: a hidden record will simply look like it does not exist (`404 RECORD_NOT_FOUND`) and disappear from lists and exports.

## The record object
`{ record_id, dependent_id, category, title, notes, record_date, has_file, file_name, content_type, size_bytes, file_path, uploaded_by, uploaded_by_name, uploaded_at, can_modify, already_saved }`
`file_path` is the address of the file (send the login token), or null for a note-only record. `already_saved` is only meaningful on `POST`.

## Endpoints (`{id}` = the Dependent's user id)
| Method and path | What |
|---|---|
| POST `/dependents/{id}/records` | Add a record. **Multipart form**: `category`, `title` (1 to 150), `record_date` (`YYYY-MM-DD`, not before 1900, not after tomorrow), optional `notes` (up to 5000), optional `client_id`, optional `file`. `201` new, `200` repeat |
| GET `/dependents/{id}/records` | List, newest record date first. Query: `category`, `year`, `month` (needs `year`), `limit` (1 to 100, default 30), `offset`. Reply `{ items, total, limit, offset }` |
| GET `/dependents/{id}/records/{record_id}` | One record |
| GET `/dependents/{id}/records/{record_id}/file` | The original file (decrypted). `Content-Type` is the real type, `Content-Disposition: attachment`. `404 NO_FILE` for a note-only record |
| PATCH `/dependents/{id}/records/{record_id}` | Change `title`, `category`, `record_date`, `notes` (send only what changes; `notes: ""` clears it). The file cannot be replaced: delete and add again |
| DELETE `/dependents/{id}/records/{record_id}` | Delete the record and its file. `204` |
| GET `/dependents/{id}/records/export` | PDF. Query: `scope` = `complete` (default) / `year` (+ `year`) / `month` (+ `year`, `month`). Wrong combination = `422` |

### What is in the PDF
A front page with the person's name, the period, and a table of every record; then each record's note, **pictures** shown under their record, and every **attached PDF** added after the summary (damaged or password-protected PDFs are listed as "Not included"). At most **200** records per export (the newest; the PDF says so; export a year or a month to get the rest) and about 60 MB of files in total. Text is shown in a Western font: Urdu script in a title or note shows as `?` in the PDF (the app still shows it correctly).

## Doctor link (FR-G3)
| Method and path | What |
|---|---|
| POST `/dependents/{id}/records/share` | Make a link. Body (all optional): `scope` (`complete` / `year` / `month`), `year`, `month`, `hours` (1 to 720, default **72**), `categories` (default: all you may see). `201` with the link **and its secret `token`, shown only now** |
| GET `/dependents/{id}/records/share` | The links: `{ items: [ { share_id, scope, year, month, categories, created_at, expires_at, revoked_at, status, open_count, last_opened_at, created_by } ] }`. `status` = `active` / `expired` / `revoked`. The Dependent and the Primary see all links; a Secondary only their own |
| DELETE `/dependents/{id}/records/share/{share_id}` | Cancel a link (the person who made it, the Primary, or the Dependent). Safe to repeat |
| GET `/shared/records/{token}` | **What the doctor opens. No login.** Answers with the PDF (`inline`, never cached, not indexed) |

The create reply also has `url`: `/shared/records/<token>` (or the full address when the server knows its public address). Show it so it can be shared by WhatsApp or SMS; **the app must add the server address in front if `url` starts with `/`**. The server stores only a hash of the token, so a lost link cannot be shown again: make a new one.
The link shows the records **as they are when it is opened** (a record added later appears; a deleted one disappears). A link made by a Secondary stops working if the Primary removes that Secondary's `health_records` permission. Up to **10** open links per Dependent (`409 SHARE_LIMIT`).

## Errors
| Code | Status | When |
|---|---|---|
| `NOT_AUTHENTICATED` | 401 | no / bad token |
| `FORBIDDEN` | 403 | a Dependent using another person's vault |
| `NOT_LINKED_TO_DEPENDENT` | 403 | a Guardian who is not linked |
| `MODULE_ACCESS_DENIED` | 403 | Secondary without `health_records` (details: `module`) |
| `GUARDIAN_NOT_VERIFIED` | 403 | the Guardian has not verified phone or CNIC |
| `RECORD_MODIFY_DENIED` | 403 | changing or deleting a record someone else added (and you are not the Primary) |
| `SHARE_MODIFY_DENIED` | 403 | cancelling a link you may not cancel |
| `CATEGORY_NOT_ALLOWED` | 403 | using a category you may not (Task 5.2) |
| `RECORD_NOT_FOUND`, `NO_FILE`, `FILE_NOT_FOUND`, `SHARE_NOT_FOUND` | 404 | unknown id, no file on the record, file missing on the server, unknown link |
| `RECORDS_LIMIT`, `CLIENT_ID_REUSED`, `SHARE_LIMIT` | 409 | 500 records, retry id reused, 10 open links |
| `SHARE_EXPIRED`, `SHARE_REVOKED` | 410 | the doctor opens a link that ran out or was cancelled |
| `FILE_TOO_LARGE` | 413 | file over 10 MB |
| `UNSUPPORTED_FILE` | 415 | not a PDF, JPEG or PNG |
| `VALIDATION_ERROR`, `RECORD_NEEDS_CONTENT`, `INVALID_DATE` | 422 | bad field / nothing to save / date out of range |
| `FILE_UNREADABLE` | 500 | the stored file is damaged (the server detected a change) |

## What the screens do
- **List:** show `title`, `category`, `record_date`; a file icon if `has_file`; edit / delete only when `can_modify`. Load more with `offset`.
- **Add:** send the form as `multipart/form-data`. Create the `client_id` once per record, before the first try, and reuse it for retries. Show a progress bar for large photos.
- **Open a file:** `GET file_path` with the login token. Pictures can be shown in the app; PDFs open in the phone's viewer.
- **Export:** one button with three choices (all / this year / this month), then save or share the PDF.
- **Doctor link:** after `POST .../share`, show the link and the expiry time, with a Share button. Keep the list of links so it can be cancelled.
