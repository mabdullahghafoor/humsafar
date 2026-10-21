"""
Task 1.1 verification script.

Run from the `backend/` folder with your venv activated:
    python -m scripts.verify_models

Checks, WITHOUT touching your database:
  1. All models import without error.
  2. Exactly the 27 tables of SDS 9.2 exist, with SDS-exact table names.
  3. Every SDS column name exists on its table (traceability).
  4. The SDS 9.4 constraints exist (unique link, partial unique primary index,
     role/tier checks, NOT NULL on safety-critical status columns).
  5. The whole schema compiles to valid PostgreSQL DDL.
"""

import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.database import Base

# Table -> key columns, copied from SDS 9.2 (pages 14-16).
SDS_SCHEMA = {
    "users": ["user_id", "email", "phone", "password_hash", "role", "created_at"],
    "guardian_profiles": ["user_id", "cnic_verified", "phone_verified", "guardian_role"],
    "dependent_profiles": ["user_id", "cnic", "liveness_status", "dob", "condition_notes"],
    "guardian_dependent_links": ["link_id", "guardian_id", "dependent_id", "role", "status", "linked_at"],
    "permission_grants": ["grant_id", "link_id", "module", "granted", "updated_at"],
    "geofences": ["geofence_id", "dependent_id", "name", "lat", "lng", "radius_m", "created_by"],
    "location_logs": ["log_id", "dependent_id", "lat", "lng", "recorded_at", "battery_level"],
    "medication_schedules": ["schedule_id", "dependent_id", "drug_name", "dosage", "time_of_day", "frequency", "created_by"],
    "medication_confirmations": ["confirmation_id", "schedule_id", "scheduled_for", "confirmed_at", "status"],
    "wellness_check_schedules": ["wc_id", "dependent_id", "time_window", "grace_period_min"],
    "wellness_check_responses": ["response_id", "wc_id", "prompted_at", "responded_at", "status"],
    "escalation_events": ["event_id", "dependent_id", "trigger_type", "tier", "status", "created_at", "resolved_at"],
    "emergency_contacts": ["contact_id", "dependent_id", "name", "phone"],
    "medical_records": ["record_id", "dependent_id", "type", "file_url", "uploaded_by", "uploaded_at"],
    "vital_readings": ["reading_id", "dependent_id", "metric_type", "value", "recorded_by", "recorded_at", "source"],
    "appointments": ["appointment_id", "dependent_id", "provider_name", "scheduled_at", "notes"],
    "wearable_devices": ["device_id", "dependent_id", "ble_address", "paired_at", "last_sync_at"],
    "healthcare_organizations": ["org_id", "name", "type", "phone", "lat", "lng"],
    "home_care_providers": ["provider_id", "name", "specialization", "service_charge", "contact"],
    "booking_requests": ["request_id", "dependent_id", "provider_id", "status", "requested_at"],
    "activity_log": ["activity_id", "dependent_id", "type", "reference_id", "occurred_at"],
    "messages": ["message_id", "sender_id", "receiver_id", "type", "content_url", "priority", "sent_at"],
    "call_logs": ["call_id", "caller_id", "callee_id", "type", "started_at", "duration_s"],
    "notifications": ["notification_id", "user_id", "type", "priority", "payload", "sent_at", "acknowledged_at"],
    "camera_devices": ["camera_id", "dependent_id", "stream_uri", "paired_at"],
    "camera_clips": ["clip_id", "dependent_id", "trigger_type", "file_url", "captured_at"],
    "audit_logs": ["audit_id", "actor_id", "action", "target_type", "target_id", "occurred_at"],
}

failures: list[str] = []


def check(condition: bool, ok_msg: str, fail_msg: str) -> None:
    if condition:
        print(f"  [PASS] {ok_msg}")
    else:
        print(f"  [FAIL] {fail_msg}")
        failures.append(fail_msg)


# Tables added AFTER the SDS freeze, each recorded in docs/backend/sds_clarifications.md.
APPROVED_EXTRA_TABLES = {"push_tokens"}  # item 29 (Task 3.1)


def main() -> None:
    tables = Base.metadata.tables

    print("1. Table count and names")
    check(len(SDS_SCHEMA) == 27, "SDS reference list has 27 tables", "reference list is not 27")
    check(len(tables) == 27 + len(APPROVED_EXTRA_TABLES), f"models define {len(tables)} tables (27 SDS + {len(APPROVED_EXTRA_TABLES)} approved)", f"models define {len(tables)} tables, expected {27 + len(APPROVED_EXTRA_TABLES)}")
    missing = sorted(set(SDS_SCHEMA) - set(tables))
    extra = sorted(set(tables) - set(SDS_SCHEMA) - APPROVED_EXTRA_TABLES)
    check(not missing, "no SDS table is missing", f"missing tables: {missing}")
    check(not extra, "no extra tables beyond the SDS", f"extra tables: {extra}")

    print("2. Column names match SDS 9.2")
    for name, cols in SDS_SCHEMA.items():
        if name not in tables:
            continue
        have = {c.name for c in tables[name].columns}
        gap = [c for c in cols if c not in have]
        check(not gap, f"{name}", f"{name} is missing columns {gap}")

    print("3. SDS 9.4 constraints")
    links = tables["guardian_dependent_links"]
    index_names = {i.name for i in links.indexes}
    check("uq_one_primary_per_dependent" in index_names, "partial unique index: one Primary per Dependent", "partial unique index missing")
    primary_idx = next((i for i in links.indexes if i.name == "uq_one_primary_per_dependent"), None)
    if primary_idx is not None:
        check(primary_idx.unique, "primary-guardian index is UNIQUE", "primary-guardian index is not unique")
        where = str(primary_idx.dialect_options["postgresql"]["where"])
        check("primary" in where, f"index predicate is: {where}", f"unexpected index predicate: {where}")
    uniques = [sorted(c.name for c in u.columns) for u in links.constraints if u.__class__.__name__ == "UniqueConstraint"]
    check(["dependent_id", "guardian_id"] in uniques, "unique (guardian_id, dependent_id)", "unique (guardian_id, dependent_id) missing")
    link_checks = " ".join(str(c.sqltext) for c in links.constraints if c.__class__.__name__ == "CheckConstraint")
    check("'primary'" in link_checks and "'secondary'" in link_checks, "links.role CHECK primary/secondary", "links.role CHECK missing")
    esc_checks = " ".join(str(c.sqltext) for c in tables["escalation_events"].constraints if c.__class__.__name__ == "CheckConstraint")
    check("external_contact" in esc_checks, "escalation_events.tier CHECK present", "escalation_events.tier CHECK missing")
    check(not tables["medication_confirmations"].c.status.nullable, "medication_confirmations.status NOT NULL", "medication_confirmations.status is nullable")
    check(not tables["wellness_check_responses"].c.status.nullable, "wellness_check_responses.status NOT NULL", "wellness_check_responses.status is nullable")

    print("4. Foreign keys: NOT NULL and no cascade deletes")
    nullable_fks = []
    cascades = []
    for t in tables.values():
        for fk in (f for c in t.columns for f in c.foreign_keys):
            if fk.parent.nullable and not fk.parent.primary_key:
                nullable_fks.append(f"{t.name}.{fk.parent.name}")
            if (fk.ondelete or "").upper() == "CASCADE":
                cascades.append(f"{t.name}.{fk.parent.name}")
    print(f"       nullable FKs (documented exception): {nullable_fks}")
    check(nullable_fks == ["vital_readings.recorded_by"], "only vital_readings.recorded_by is a nullable FK", f"unexpected nullable FKs: {nullable_fks}")
    check(not cascades, "no ON DELETE CASCADE anywhere", f"cascade deletes found: {cascades}")

    print("5. Compiles to PostgreSQL DDL")
    dialect = postgresql.dialect()
    try:
        for t in Base.metadata.sorted_tables:
            str(CreateTable(t).compile(dialect=dialect))
            for idx in t.indexes:
                str(CreateIndex(idx).compile(dialect=dialect))
        check(True, "all CREATE TABLE / CREATE INDEX statements compile", "")
    except Exception as exc:  # noqa: BLE001
        check(False, "", f"DDL compile error: {exc}")

    print("6. ORM relationships resolve")
    try:
        from sqlalchemy.orm import configure_mappers

        configure_mappers()
        check(True, "all relationship() definitions configure cleanly", "")
    except Exception as exc:  # noqa: BLE001
        check(False, "", f"mapper configuration error: {exc}")

    print()
    if failures:
        print(f"RESULT: {len(failures)} check(s) FAILED")
        sys.exit(1)
    print("RESULT: all checks passed. Models match SDS 9.2 / 9.4.")


if __name__ == "__main__":
    main()
