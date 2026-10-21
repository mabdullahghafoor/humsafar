"""
Encryption and transport audit (Task 6.5, FR-N1 / FR-N2). Run it against any environment:

    python -m app.scripts.security_audit

It checks the live settings, the database connection, how secrets are stored and whether the stored files on disk are really
encrypted, then prints PASS / WARN / FAIL per line and the data inventory (what is protected how). Exit code 1 when any line FAILs.
In ENVIRONMENT=production a WARN about a missing control counts as FAIL.
"""

import re
import sys
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.transport import production_problems
from app.models import CameraClip, MedicalRecord, RecordShare, User
from app.services import crypto_service, storage_service

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str


# What is protected how. Kept here so the audit, the tests and docs/backend/security_encryption.md say the same thing.
INVENTORY = [
    ("Passwords", "users.password_hash", "bcrypt (12 rounds), salted; never stored or logged in clear", "application"),
    ("Doctor-link and invite secrets", "record_shares.token_hash, signed invite tokens", "only a SHA-256 hash of a doctor-link secret is stored; invites are signed, not stored", "application"),
    ("Medical record files (PDF / JPEG / PNG)", "RECORDS_STORAGE_DIR", "AES-256-GCM before saving (key RECORDS_ENCRYPTION_KEY); tampering is detected", "application, file level (FR-N2)"),
    ("Emergency camera clips", "CLIPS_STORAGE_DIR", "AES-256-GCM before saving (same key and cipher)", "application, file level (FR-N2)"),
    ("Record titles and notes, manual vitals, band readings, location history, messages", "PostgreSQL tables", "encrypted at rest by the database host's disk encryption (SDS 17: 'database/storage layer'); the connection uses TLS (sslmode=require). Not encrypted per column: the values are used by SQL range checks, geofence and analytics queries", "database / storage layer (FR-N2)"),
    ("Voice message audio", "VOICE_STORAGE_DIR", "server disk, protected by the host's volume encryption (not in the FR-N2 list)", "storage layer"),
    ("Client to server traffic", "HTTPS", "TLS 1.2+ ends at the host's proxy; ENFORCE_HTTPS refuses plain http, HSTS and hardening headers are sent", "transport (FR-N1)"),
    ("Calls and live camera video", "hosted RTC room (ZegoCloud)", "encrypted in transit by the provider; NOT end-to-end encrypted (clarification 140, 148)", "transport (FR-N1)"),
    ("Sessions", "JWT access (15 min) and refresh (7 days) tokens", "signed with JWT_SECRET_KEY (HS256)", "application"),
]


def _settings_checks() -> list[Check]:
    s = get_settings()
    errors, warnings = production_problems(s)
    prod = s.ENVIRONMENT == "production"
    out = []
    for e in errors:
        out.append(Check("Settings", FAIL if prod else WARN, e + ("" if prod else " (fine for development)")))
    for w in warnings:
        out.append(Check("Settings", WARN, w))
    if not errors:
        out.append(Check("Settings", PASS, "secrets, TLS enforcement and rate limits are configured for production"))
    return out


def _db_checks(db: Session) -> list[Check]:
    out = []
    ssl = db.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")).scalar()
    local = get_settings().DATABASE_URL.split("@")[-1].split("/")[0].split(":")[0] in ("localhost", "127.0.0.1", "")
    out.append(Check("Database connection TLS", PASS if ssl else (WARN if local else FAIL), "TLS in use" if ssl else "no TLS" + (" (local development database)" if local else " to a remote database")))
    bad = db.scalar(select(func.count()).select_from(User).where(~User.password_hash.like("$2%"))) or 0
    out.append(Check("Passwords hashed", FAIL if bad else PASS, f"{bad} account(s) with a non-bcrypt value" if bad else "every password is a bcrypt hash"))
    hashes = db.scalars(select(RecordShare.token_hash)).all()
    bad = [h for h in hashes if not re.fullmatch(r"[0-9a-f]{64}", h or "")]
    out.append(Check("Doctor-link secrets hashed", FAIL if bad else PASS, f"{len(bad)} link(s) not stored as a SHA-256 hash" if bad else f"{len(hashes)} link(s), hashes only"))
    return out


def _file_checks(db: Session) -> list[Check]:
    out = []
    for kind, model, label in (("records", MedicalRecord, "Record files"), ("clips", CameraClip, "Camera clips")):
        keys = [k for (k,) in db.execute(select(model.file_url).where(model.file_url.is_not(None))).all()]
        store = storage_service.get_storage(kind)
        plain, missing = 0, 0
        for k in keys:
            p = store.path(k)
            if p is None:
                missing += 1
                continue
            with p.open("rb") as f:
                if f.read(len(crypto_service.MAGIC)) != crypto_service.MAGIC:
                    plain += 1
        if plain:
            out.append(Check(f"{label} encrypted on disk", FAIL, f"{plain} of {len(keys)} file(s) are NOT encrypted"))
        else:
            note = f"; {missing} file(s) missing on this machine" if missing else ""
            out.append(Check(f"{label} encrypted on disk", WARN if missing and not len(keys) - missing else PASS, f"{len(keys) - missing} file(s) checked, all encrypted{note}"))
    return out


def run(db: Session) -> list[Check]:
    return _settings_checks() + _db_checks(db) + _file_checks(db)


def main() -> int:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        checks = run(db)
    finally:
        db.close()
    prod = get_settings().ENVIRONMENT == "production"
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"{c.status:5} {c.name.ljust(width)}  {c.detail}")
    print("\nWhat is protected how:")
    for what, where, how, layer in INVENTORY:
        print(f" - {what} [{where}]: {how} ({layer})")
    failed = [c for c in checks if c.status == FAIL or (prod and c.status == WARN)]
    print(f"\n{'FAILED' if failed else 'OK'}: {len(failed)} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
