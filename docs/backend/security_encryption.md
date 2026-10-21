# Encryption and transport security (Task 6.5, FR-N1 / FR-N2)

Answers SDS section 17. Check any environment with `python -m app.scripts.security_audit` (exit code 1 on a FAIL; in production a WARN also fails).

## What is protected how
| Data | Where | Protection | Layer |
|---|---|---|---|
| Passwords | `users.password_hash` | bcrypt, 12 rounds, salted | application |
| Doctor-link secrets | `record_shares.token_hash` | only a SHA-256 hash is stored | application |
| Medical record files | `RECORDS_STORAGE_DIR` | AES-256-GCM before saving, tampering detected | application, file level (FR-N2) |
| Emergency camera clips | `CLIPS_STORAGE_DIR` | AES-256-GCM before saving | application, file level (FR-N2) |
| Record titles / notes, manual vitals, band readings, location history, messages | PostgreSQL | encrypted at rest by the database host's disk encryption; TLS connection | database / storage layer (FR-N2) |
| Voice message audio | `VOICE_STORAGE_DIR` | server disk, host volume encryption | storage layer |
| Client to server traffic | HTTPS | TLS 1.2+ at the host proxy; `ENFORCE_HTTPS`, HSTS, hardening headers | transport (FR-N1) |
| Calls and live camera video | hosted RTC room (ZegoCloud) | encrypted in transit by the provider; **not** end-to-end | transport (FR-N1) |
| Sessions | JWT access 15 min, refresh 7 days | signed (HS256) | application |

Why structured data is not encrypted per column: the values are read by SQL (range checks, geofence, analytics in Phase 7). Encrypting each column would make those impossible or slow, and the SDS asks for the "database/storage layer". If the supervisor requires column-level encryption, record notes are the first candidate.

## Settings that matter in production
`ENVIRONMENT=production` refuses to start unless `JWT_SECRET_KEY` and `RECORDS_ENCRYPTION_KEY` are 32+ characters, `DEBUG=false`, `ENFORCE_HTTPS=true`, `RATE_LIMIT_ENABLED=true` and a remote database URL has `sslmode=require`. Behind a proxy set `TRUST_PROXY_HEADERS=true`. Back up `RECORDS_ENCRYPTION_KEY` outside the repo and never change it.

## Rate limits (SDS 17)
8 wrong passwords per email in 5 minutes; 5 wrong phone codes or Dependent-KYC passwords in 5 minutes; 60 login / refresh and 60 register calls per minute per IP. Answer `429 TOO_MANY_REQUESTS` with `Retry-After`.

## What to say in the report
"All traffic uses TLS. Audio and video are encrypted in transit through the video provider. Medical record files and emergency clips are encrypted with AES-256-GCM before storage; the database and its backups are encrypted at rest by the database host."
