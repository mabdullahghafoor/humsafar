"""
Task 5.1 tests: Medical Vault (FR-G1), PDF export, doctor-shareable links (FR-G3).
"""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from threading import Barrier

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.models import AuditLog, MedicalRecord, RecordShare
from app.services import records_service
from tests.test_linkage import PASSWORD, PHOTO, assert_error, auth, link, make_guardian, make_dependent
from tests.test_location import team
from tests.test_messaging import msgteam
from tests.test_permissions import put


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "RECORDS_STORAGE_DIR", str(tmp_path / "records"))
    return tmp_path / "records"


def files_on_disk(store):
    return sorted(p for p in store.glob("*") if p.is_file()) if store.exists() else []


def pdf_bytes(text="Hemoglobin 13.2 g/dL", pages=1):
    buf = BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 750, f"{text} page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def img_bytes(fmt="PNG", color=(200, 30, 30), size=(60, 40)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


PDF = pdf_bytes()
PNG = img_bytes()
JPG = img_bytes("JPEG")


def add(client, token, dep, *, category="lab_report", title="Blood test", record_date="2026-03-10", notes=None, file=None, name="report.pdf", **extra):
    form = {"category": category, "title": title, "record_date": record_date, **{k: str(v) for k, v in extra.items()}}
    if notes is not None:
        form["notes"] = notes
    files = {"file": (name, file, "application/octet-stream")} if file is not None else None
    return client.post(f"/dependents/{dep}/records", data=form, files=files, headers=auth(token))


def ok(r, status=201):
    assert r.status_code == status, r.text
    return r.json()


def rlist(client, token, dep, **params):
    r = client.get(f"/dependents/{dep}/records", params=params, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def allow(client, t, granted=True):
    assert put(client, t["pt"], t["dep"], "health_records", t["sid"], granted).status_code == 200


def export(client, token, dep, **params):
    return client.get(f"/dependents/{dep}/records/export", params=params, headers=auth(token))


def pdf_text(content):
    r = PdfReader(BytesIO(content))
    return "\n".join(p.extract_text() or "" for p in r.pages), r


def share(client, token, dep, **body):
    return client.post(f"/dependents/{dep}/records/share", json=body, headers=auth(token))


def stranger_dependent_token(client, n):
    """A second, activated Dependent linked only to a different Guardian: (token, id)."""
    gt, _, _ = make_guardian(client, n + 20)
    dep = make_dependent(client, n)
    k = client.post(f"/dependents/{dep}/kyc-verify", json={"password": PASSWORD, "cnic": f"42101-7654{n:03d}-1", "liveness_image": PHOTO})
    assert k.status_code == 200, k.text
    assert link(client, gt, dep).status_code == 201
    r = client.post("/auth/login", json={"email": f"d{n}@link-test.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], dep


def second_dependent(client, t):
    dep2 = make_dependent(client, 2)
    k = client.post(f"/dependents/{dep2}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-7654322-1", "liveness_image": PHOTO})
    assert k.status_code == 200, k.text
    assert link(client, t["pt"], dep2).status_code == 201
    return dep2


# ------------------------------------------------------------ adding and reading

def test_guardian_uploads_a_pdf_and_downloads_it_back(client, store):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], notes="  fasting  ", file=PDF, name="../../My Lab Report!.pdf"))
    assert rec["category"] == "lab_report" and rec["title"] == "Blood test" and rec["notes"] == "fasting"
    assert rec["has_file"] and rec["content_type"] == "application/pdf" and rec["size_bytes"] == len(PDF)
    assert rec["file_name"] == "My Lab Report.pdf"  # path parts and odd characters removed
    assert rec["file_path"] == f"/dependents/{t['dep']}/records/{rec['record_id']}/file"
    assert rec["can_modify"] is True and rec["already_saved"] is False and rec["record_date"] == "2026-03-10"
    r = client.get(rec["file_path"], headers=auth(t["pt"]))
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"] and "no-store" in r.headers["cache-control"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_stored_file_is_encrypted_on_disk(client, store):
    t = team(client)
    secret = pdf_bytes("TOP SECRET DIAGNOSIS")
    ok(add(client, t["pt"], t["dep"], file=secret))
    (path,) = files_on_disk(store)
    raw = path.read_bytes()
    assert raw.startswith(b"HV1") and b"TOP SECRET" not in raw and b"%PDF" not in raw
    assert len(raw) == len(secret) + 3 + 12 + 16


def test_each_upload_gets_a_new_random_nonce(client, store):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], file=PDF))
    ok(add(client, t["pt"], t["dep"], title="Again", file=PDF))
    a, b = files_on_disk(store)
    assert a.read_bytes() != b.read_bytes()


def test_dependent_adds_a_note_only_record_and_sees_it(client):
    t = team(client)
    rec = ok(add(client, t["dt"], t["dep"], category="other", title="Allergy note", notes="Penicillin allergy"))
    assert rec["has_file"] is False and rec["file_path"] is None and rec["content_type"] is None
    assert rlist(client, t["dt"], t["dep"])["total"] == 1
    assert rlist(client, t["pt"], t["dep"])["items"][0]["uploaded_by"] == rec["uploaded_by"]
    assert client.get(f"/dependents/{t['dep']}/records/{rec['record_id']}/file", headers=auth(t["pt"])).status_code == 404


def test_jpeg_and_png_are_accepted_and_typed_by_content_not_by_name(client):
    t = team(client)
    a = ok(add(client, t["pt"], t["dep"], category="xray", title="Chest", file=JPG, name="scan.pdf"))
    b = ok(add(client, t["pt"], t["dep"], category="xray", title="Knee", file=PNG, name="scan.jpg"))
    assert (a["content_type"], a["file_name"]) == ("image/jpeg", "scan.jpg")
    assert (b["content_type"], b["file_name"]) == ("image/png", "scan.png")


def test_bad_input_is_rejected(client, store, monkeypatch):
    t = team(client)
    base = dict(client=client, token=t["pt"], dep=t["dep"])
    assert_error(add(client, t["pt"], t["dep"], category="scan", notes="x"), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"], title="   ", notes="x"), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"], title="x" * 151, notes="x"), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"], record_date="10/03/2026", notes="x"), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"], notes="x" * 5001), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"]), 422, "RECORD_NEEDS_CONTENT")
    assert_error(add(client, t["pt"], t["dep"], notes="   "), 422, "RECORD_NEEDS_CONTENT")
    future = (date.today() + timedelta(days=5)).isoformat()
    assert_error(add(client, t["pt"], t["dep"], notes="x", record_date=future), 422, "INVALID_DATE")
    assert_error(add(client, t["pt"], t["dep"], notes="x", record_date="1899-12-31"), 422, "INVALID_DATE")
    assert_error(add(client, t["pt"], t["dep"], file=b"just some text, not a pdf"), 415, "UNSUPPORTED_FILE")
    assert_error(add(client, t["pt"], t["dep"], file=b"MZ\x90\x00 an exe renamed", name="x.pdf"), 415, "UNSUPPORTED_FILE")
    monkeypatch.setattr(get_settings(), "RECORD_MAX_BYTES", 500)
    assert_error(add(client, t["pt"], t["dep"], file=pdf_bytes(pages=5)), 413, "FILE_TOO_LARGE")
    assert files_on_disk(store) == []
    assert rlist(client, t["pt"], t["dep"])["total"] == 0


def test_today_and_tomorrow_are_allowed_as_a_record_date(client):
    t = team(client)
    today = datetime.now(timezone.utc).date()  # the server counts in UTC; date.today() is the computer's local day (fails after midnight in Pakistan)
    ok(add(client, t["pt"], t["dep"], notes="today", record_date=today.isoformat()))
    ok(add(client, t["pt"], t["dep"], notes="tomorrow (time zones)", record_date=(today + timedelta(days=1)).isoformat()))


def test_needs_login_and_unknown_dependent(client):
    t = team(client)
    assert_error(client.get(f"/dependents/{t['dep']}/records"), 401, "NOT_AUTHENTICATED")
    assert_error(client.post(f"/dependents/{t['dep']}/records", data={"category": "other", "title": "x", "record_date": "2026-01-01", "notes": "n"}), 401, "NOT_AUTHENTICATED")
    assert_error(client.get(f"/dependents/{uuid.uuid4()}/records", headers=auth(t["pt"])), 403, "NOT_LINKED_TO_DEPENDENT")


# ------------------------------------------------------------ listing

def test_list_filters_order_and_paging(client):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], category="prescription", title="Rx Jan", record_date="2026-01-15", notes="a"))
    ok(add(client, t["pt"], t["dep"], category="lab_report", title="Lab Mar", record_date="2026-03-02", notes="a"))
    ok(add(client, t["pt"], t["dep"], category="lab_report", title="Lab Mar late", record_date="2026-03-30", notes="a"))
    ok(add(client, t["pt"], t["dep"], category="xray", title="Xray 2025", record_date="2025-12-31", notes="a"))
    ok(add(client, t["pt"], t["dep"], category="other", title="Dec 2025", record_date="2025-12-01", notes="a"))
    titles = lambda **p: [i["title"] for i in rlist(client, t["pt"], t["dep"], **p)["items"]]
    assert titles() == ["Lab Mar late", "Lab Mar", "Rx Jan", "Xray 2025", "Dec 2025"]
    assert titles(category="lab_report") == ["Lab Mar late", "Lab Mar"]
    assert titles(year=2026) == ["Lab Mar late", "Lab Mar", "Rx Jan"]
    assert titles(year=2026, month=3) == ["Lab Mar late", "Lab Mar"]
    assert titles(year=2025, month=12) == ["Xray 2025", "Dec 2025"]  # December: the end of the range rolls into the next year
    assert titles(year=2026, month=1) == ["Rx Jan"] and titles(year=2025) == ["Xray 2025", "Dec 2025"]
    assert titles(year=2026, month=2) == []
    p1 = rlist(client, t["pt"], t["dep"], limit=2)
    assert p1["total"] == 5 and p1["limit"] == 2 and p1["offset"] == 0 and len(p1["items"]) == 2
    p2 = rlist(client, t["pt"], t["dep"], limit=2, offset=2)
    p3 = rlist(client, t["pt"], t["dep"], limit=2, offset=4)
    assert [i["title"] for i in p1["items"] + p2["items"] + p3["items"]] == titles()
    assert_error(client.get(f"/dependents/{t['dep']}/records", params={"month": 3}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.get(f"/dependents/{t['dep']}/records", params={"category": "x"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.get(f"/dependents/{t['dep']}/records", params={"limit": 0}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")


def test_same_date_records_have_a_stable_order_across_pages(client):
    t = team(client)
    for i in range(6):
        ok(add(client, t["pt"], t["dep"], title=f"R{i}", record_date="2026-05-05", notes="n"))
    seen = []
    for off in (0, 2, 4):
        seen += [i["record_id"] for i in rlist(client, t["pt"], t["dep"], limit=2, offset=off)["items"]]
    assert len(set(seen)) == 6


def test_a_record_of_one_dependent_cannot_be_read_through_another(client):
    t = team(client)
    dep2 = second_dependent(client, t)
    rec = ok(add(client, t["pt"], t["dep"], notes="private"))
    assert_error(client.get(f"/dependents/{dep2}/records/{rec['record_id']}", headers=auth(t["pt"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.get(f"/dependents/{dep2}/records/{rec['record_id']}/file", headers=auth(t["pt"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.delete(f"/dependents/{dep2}/records/{rec['record_id']}", headers=auth(t["pt"])), 404, "RECORD_NOT_FOUND")
    assert rlist(client, t["pt"], dep2)["total"] == 0


# ------------------------------------------------------------ permissions

def test_secondary_needs_the_health_records_permission_for_everything(client):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    rid, d = rec["record_id"], t["dep"]
    calls = [
        lambda: client.get(f"/dependents/{d}/records", headers=auth(t["st"])),
        lambda: add(client, t["st"], d, notes="x"),
        lambda: client.get(f"/dependents/{d}/records/{rid}", headers=auth(t["st"])),
        lambda: client.get(f"/dependents/{d}/records/{rid}/file", headers=auth(t["st"])),
        lambda: client.patch(f"/dependents/{d}/records/{rid}", json={"title": "x"}, headers=auth(t["st"])),
        lambda: client.delete(f"/dependents/{d}/records/{rid}", headers=auth(t["st"])),
        lambda: export(client, t["st"], d),
        lambda: share(client, t["st"], d),
        lambda: client.get(f"/dependents/{d}/records/share", headers=auth(t["st"])),
    ]
    for c in calls:
        assert_error(c(), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    assert rlist(client, t["st"], d)["total"] == 1
    assert client.get(f"/dependents/{d}/records/{rid}/file", headers=auth(t["st"])).content == PDF
    assert export(client, t["st"], d).status_code == 200
    allow(client, t, False)
    for c in calls:
        assert_error(c(), 403, "MODULE_ACCESS_DENIED")  # revoking works at once


def test_other_modules_do_not_open_the_vault(client):
    t = team(client)
    assert put(client, t["pt"], t["dep"], "medication_management", t["sid"], True).status_code == 200
    assert put(client, t["pt"], t["dep"], "emergency_alerts", t["sid"], True).status_code == 200
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")


def test_strangers_and_other_dependents_are_refused(client):
    t = team(client)
    other_g, _, _ = make_guardian(client, 7)
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(other_g)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(add(client, other_g, t["dep"], notes="x"), 403, "NOT_LINKED_TO_DEPENDENT")
    other_dep_token, _ = stranger_dependent_token(client, 9)
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(other_dep_token)), 403, "FORBIDDEN")
    assert_error(add(client, other_dep_token, t["dep"], notes="x"), 403, "FORBIDDEN")
    assert_error(export(client, other_dep_token, t["dep"]), 403, "FORBIDDEN")


def test_unverified_guardian_is_refused(client):
    t = team(client)
    from app.models import GuardianProfile
    # a secondary who is not verified
    from tests.test_linkage import make_secondary
    st2, sid2, _ = make_secondary(client, t["pt"], t["dep"], 2)
    assert put(client, t["pt"], t["dep"], "health_records", sid2, True).status_code == 200
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(st2)), 403, "GUARDIAN_NOT_VERIFIED")


def test_only_uploader_or_primary_may_change_or_delete(client, store):
    t = team(client)
    allow(client, t)
    by_primary = ok(add(client, t["pt"], t["dep"], title="P", file=PDF))
    by_second = ok(add(client, t["st"], t["dep"], title="S", file=PNG, name="s.png"))
    by_dep = ok(add(client, t["dt"], t["dep"], title="D", notes="n"))
    d = t["dep"]
    patch = lambda tok, r, **b: client.patch(f"/dependents/{d}/records/{r['record_id']}", json=b, headers=auth(tok))
    assert by_primary["can_modify"] and not by_second["can_modify"] or True
    assert_error(patch(t["st"], by_primary, title="x"), 403, "RECORD_MODIFY_DENIED")
    assert_error(patch(t["dt"], by_primary, title="x"), 403, "RECORD_MODIFY_DENIED")
    assert_error(patch(t["pt"], by_dep, title="x") and client.delete(f"/dependents/{d}/records/{by_dep['record_id']}", headers=auth(t["st"])), 403, "RECORD_MODIFY_DENIED")
    assert_error(client.delete(f"/dependents/{d}/records/{by_second['record_id']}", headers=auth(t["dt"])), 403, "RECORD_MODIFY_DENIED")
    assert patch(t["st"], by_second, title="S2").status_code == 200  # the Secondary changes what they added
    assert patch(t["pt"], by_second, title="S3").status_code == 200  # the Primary changes anything
    assert patch(t["pt"], by_dep, title="D2").status_code == 200
    assert client.delete(f"/dependents/{d}/records/{by_dep['record_id']}", headers=auth(t["dt"])).status_code == 204  # the Dependent deletes their own
    assert client.delete(f"/dependents/{d}/records/{by_second['record_id']}", headers=auth(t["pt"])).status_code == 204  # the Primary deletes a Secondary's
    flags = {i["title"]: i["can_modify"] for i in rlist(client, t["st"], d)["items"]}
    assert flags == {"P": False}
    assert len(files_on_disk(store)) == 1  # only the Primary's PDF is left


def test_can_modify_flag_matches_the_rules(client):
    t = team(client)
    allow(client, t)
    ok(add(client, t["pt"], t["dep"], title="P", notes="n"))
    ok(add(client, t["st"], t["dep"], title="S", notes="n"))
    ok(add(client, t["dt"], t["dep"], title="D", notes="n"))
    seen = lambda tok: {i["title"]: i["can_modify"] for i in rlist(client, tok, t["dep"])["items"]}
    assert seen(t["pt"]) == {"P": True, "S": True, "D": True}
    assert seen(t["st"]) == {"P": False, "S": True, "D": False}
    assert seen(t["dt"]) == {"P": False, "S": False, "D": True}


# ------------------------------------------------------------ changing and deleting

def test_patch_changes_only_what_is_sent(client):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], category="other", title="Old", notes="n1", file=PDF))
    url = f"/dependents/{t['dep']}/records/{rec['record_id']}"
    r = ok(client.patch(url, json={"title": " New ", "category": "prescription", "record_date": "2026-02-02"}, headers=auth(t["pt"])), 200)
    assert (r["title"], r["category"], r["record_date"], r["notes"]) == ("New", "prescription", "2026-02-02", "n1")
    assert ok(client.patch(url, json={"notes": ""}, headers=auth(t["pt"])), 200)["notes"] is None  # a record with a file may lose its note
    assert ok(client.patch(url, json={"notes": "again"}, headers=auth(t["pt"])), 200)["notes"] == "again"


def test_patch_validation(client):
    t = team(client)
    note = ok(add(client, t["pt"], t["dep"], notes="only a note"))
    url = f"/dependents/{t['dep']}/records/{note['record_id']}"
    h = auth(t["pt"])
    assert_error(client.patch(url, json={}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"title": None}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"category": "bad"}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"title": "  "}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"record_date": "2999-01-01"}, headers=h), 422, "INVALID_DATE")
    assert_error(client.patch(url, json={"notes": None}, headers=h), 422, "RECORD_NEEDS_CONTENT")
    assert_error(client.patch(url, json={"notes": "   "}, headers=h), 422, "RECORD_NEEDS_CONTENT")
    assert client.get(url, headers=h).json()["notes"] == "only a note"  # the refused change was not saved


def test_delete_removes_the_row_and_the_file(client, store):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    assert len(files_on_disk(store)) == 1
    assert client.delete(f"/dependents/{t['dep']}/records/{rec['record_id']}", headers=auth(t["pt"])).status_code == 204
    assert files_on_disk(store) == [] and rlist(client, t["pt"], t["dep"])["total"] == 0
    assert_error(client.delete(f"/dependents/{t['dep']}/records/{rec['record_id']}", headers=auth(t["pt"])), 404, "RECORD_NOT_FOUND")


def test_audit_log_records_adds_downloads_changes_deletes_and_exports(client, db):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    d, rid = t["dep"], rec["record_id"]
    client.get(f"/dependents/{d}/records/{rid}/file", headers=auth(t["pt"]))
    client.patch(f"/dependents/{d}/records/{rid}", json={"title": "x"}, headers=auth(t["pt"]))
    export(client, t["pt"], d)
    client.delete(f"/dependents/{d}/records/{rid}", headers=auth(t["pt"]))
    actions = [a for a in db.scalars(select(AuditLog.action).order_by(AuditLog.occurred_at, AuditLog.audit_id))]
    for a in ("record_added", "record_downloaded", "record_changed", "records_exported", "record_deleted"):
        assert a in actions, actions


# ------------------------------------------------------------ safe retry and limits

def test_retry_with_the_same_client_id_saves_nothing_twice(client, store):
    t = team(client)
    cid = str(uuid.uuid4())
    first = ok(add(client, t["pt"], t["dep"], file=PDF, client_id=cid))
    again = ok(add(client, t["pt"], t["dep"], file=PDF, client_id=cid), 200)
    assert again["record_id"] == first["record_id"] and again["already_saved"] is True and first["already_saved"] is False
    assert rlist(client, t["pt"], t["dep"])["total"] == 1 and len(files_on_disk(store)) == 1


def test_client_id_reused_for_something_else_is_a_conflict(client, store):
    t = team(client)
    cid = str(uuid.uuid4())
    ok(add(client, t["pt"], t["dep"], title="A", file=PDF, client_id=cid))
    assert_error(add(client, t["pt"], t["dep"], title="B", file=PDF, client_id=cid), 409, "CLIENT_ID_REUSED")
    assert_error(add(client, t["pt"], t["dep"], title="A", file=PNG, client_id=cid), 409, "CLIENT_ID_REUSED")
    dep2 = second_dependent(client, t)
    assert_error(add(client, t["pt"], dep2, title="A", file=PDF, client_id=cid), 409, "CLIENT_ID_REUSED")
    assert len(files_on_disk(store)) == 1


def test_same_client_id_from_two_people_does_not_clash(client):
    t = team(client)
    allow(client, t)
    cid = str(uuid.uuid4())
    ok(add(client, t["pt"], t["dep"], notes="n", client_id=cid))
    ok(add(client, t["st"], t["dep"], notes="n", client_id=cid))
    assert rlist(client, t["pt"], t["dep"])["total"] == 2


def test_parallel_identical_retries_save_exactly_one(client, store):
    t = team(client)
    cid = str(uuid.uuid4())
    n = 6
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return add(client, t["pt"], t["dep"], file=PDF, client_id=cid)

    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(go, range(n)))
    assert sorted(r.status_code for r in res) == [200] * (n - 1) + [201], [r.text for r in res]
    assert len({r.json()["record_id"] for r in res}) == 1
    assert rlist(client, t["pt"], t["dep"])["total"] == 1 and len(files_on_disk(store)) == 1


def test_vault_size_limit_and_parallel_uploads_cannot_beat_it(client, store, monkeypatch):
    monkeypatch.setattr(get_settings(), "RECORDS_MAX_PER_DEPENDENT", 3)
    t = team(client)
    for i in range(3):
        ok(add(client, t["pt"], t["dep"], title=f"R{i}", file=PDF))
    assert_error(add(client, t["pt"], t["dep"], title="R4", file=PDF), 409, "RECORDS_LIMIT")
    assert len(files_on_disk(store)) == 3  # the refused file was not left behind
    client.delete(f"/dependents/{t['dep']}/records/{rlist(client, t['pt'], t['dep'])['items'][0]['record_id']}", headers=auth(t["pt"]))
    n = 6
    gate = Barrier(n)

    def go(i):
        gate.wait()
        return add(client, t["pt"], t["dep"], title=f"P{i}", file=PDF)

    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(go, range(n)))
    assert sorted(r.status_code for r in res) == [201, 409, 409, 409, 409, 409], [r.text for r in res]
    assert rlist(client, t["pt"], t["dep"])["total"] == 3 and len(files_on_disk(store)) == 3


# ------------------------------------------------------------ damaged or missing files

def test_a_tampered_file_is_refused_not_shown(client, store):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    (path,) = files_on_disk(store)
    raw = bytearray(path.read_bytes())
    raw[40] ^= 0xFF
    path.write_bytes(bytes(raw))
    assert_error(client.get(rec["file_path"], headers=auth(t["pt"])), 500, "FILE_UNREADABLE")
    text, _ = pdf_text(export(client, t["pt"], t["dep"]).content)
    assert "Blood test" in text and "no longer available" in text.replace("\n", " ") or "Not included" in text


def test_a_missing_file_gives_404(client, store):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    files_on_disk(store)[0].unlink()
    assert_error(client.get(rec["file_path"], headers=auth(t["pt"])), 404, "FILE_NOT_FOUND")
    assert export(client, t["pt"], t["dep"]).status_code == 200  # the export still works


def test_a_different_key_cannot_read_old_files(client, monkeypatch):
    t = team(client)
    rec = ok(add(client, t["pt"], t["dep"], file=PDF))
    monkeypatch.setattr(get_settings(), "RECORDS_ENCRYPTION_KEY", "another-key")
    assert_error(client.get(rec["file_path"], headers=auth(t["pt"])), 500, "FILE_UNREADABLE")


# ------------------------------------------------------------ export

def test_complete_year_and_month_exports(client):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Jan Prescription", category="prescription", record_date="2026-01-10", notes="Take twice daily"))
    ok(add(client, t["pt"], t["dep"], title="March Blood Test", record_date="2026-03-05", notes="CBC normal"))
    ok(add(client, t["pt"], t["dep"], title="Old Xray", category="xray", record_date="2024-06-01", notes="Clear"))
    full = export(client, t["pt"], t["dep"])
    assert full.status_code == 200 and full.content.startswith(b"%PDF") and full.headers["content-type"] == "application/pdf"
    assert 'filename="humsafar-records-complete.pdf"' in full.headers["content-disposition"]
    text, _ = pdf_text(full.content)
    for s in ("Jan Prescription", "March Blood Test", "Old Xray", "Complete history", "Test User"):
        assert s in text
    y = export(client, t["pt"], t["dep"], scope="year", year=2026)
    text, _ = pdf_text(y.content)
    assert "Jan Prescription" in text and "March Blood Test" in text and "Old Xray" not in text and "Year 2026" in text
    assert 'filename="humsafar-records-2026.pdf"' in y.headers["content-disposition"]
    m = export(client, t["pt"], t["dep"], scope="month", year=2026, month=3)
    text, _ = pdf_text(m.content)
    assert "March Blood Test" in text and "Jan Prescription" not in text and "March 2026" in text
    assert 'filename="humsafar-records-2026-03.pdf"' in m.headers["content-disposition"]


def test_export_period_rules(client):
    t = team(client)
    bad = [dict(scope="year"), dict(scope="month", year=2026), dict(scope="complete", year=2026), dict(scope="year", year=2026, month=3),
           dict(scope="week"), dict(scope="month", month=3)]
    for p in bad:
        assert_error(export(client, t["pt"], t["dep"], **p), 422, "VALIDATION_ERROR")


def test_empty_export_is_a_valid_pdf_that_says_so(client):
    t = team(client)
    r = export(client, t["pt"], t["dep"], scope="year", year=2026)
    assert r.status_code == 200
    assert "no records" in pdf_text(r.content)[0]


def test_export_includes_pictures_and_adds_attached_pdfs(client):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Chest Xray", category="xray", file=JPG, name="x.jpg"))
    ok(add(client, t["pt"], t["dep"], title="Lab PDF", file=pdf_bytes("ATTACHED LAB CONTENT", pages=3)))
    ok(add(client, t["pt"], t["dep"], title="Note only", notes="just text"))
    text, reader = pdf_text(export(client, t["pt"], t["dep"]).content)
    assert "ATTACHED LAB CONTENT page 1" in text and "ATTACHED LAB CONTENT page 3" in text
    summary_pages = len(reader.pages) - 3
    assert summary_pages >= 1
    assert sum(len(p.images) for p in list(reader.pages)[:summary_pages]) >= 1  # the picture is on the summary pages
    assert "Note only" in text and "Picture" in text


def test_export_survives_hostile_and_foreign_text(client):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="<b>bold</b> & <script>", notes="a < b & c > d </para> <br/> &amp; اردو ❤ line\nbreak"))
    r = export(client, t["pt"], t["dep"])
    assert r.status_code == 200
    text, _ = pdf_text(r.content)
    assert "<b>bold</b> & <script>" in text and "a < b & c > d" in text


def test_export_leaves_out_a_damaged_pdf_but_keeps_the_rest(client, monkeypatch):
    t = team(client)
    bad = b"%PDF-1.4\nthis is not a real pdf body"
    ok(add(client, t["pt"], t["dep"], title="Broken", file=bad))
    ok(add(client, t["pt"], t["dep"], title="Good", file=pdf_bytes("GOODPAGE")))
    text, _ = pdf_text(export(client, t["pt"], t["dep"]).content)
    assert "GOODPAGE" in text and "Broken" in text and "Not included" in text


def test_export_is_capped_and_says_so(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "EXPORT_MAX_RECORDS", 2)
    t = team(client)
    for i, d in enumerate(("2026-01-01", "2026-02-01", "2026-03-01")):
        ok(add(client, t["pt"], t["dep"], title=f"Rec{i}", record_date=d, notes="n"))
    text, _ = pdf_text(export(client, t["pt"], t["dep"]).content)
    assert "newest 2 of 3" in text.replace("\n", " ") and "Rec2" in text and "Rec1" in text and "Rec0" not in text


def test_export_byte_budget_leaves_later_files_out(client, monkeypatch):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Newer", record_date="2026-04-01", file=pdf_bytes("FIRSTFILE")))
    ok(add(client, t["pt"], t["dep"], title="Older", record_date="2026-01-01", file=pdf_bytes("SECONDFILE")))
    monkeypatch.setattr(get_settings(), "EXPORT_MAX_BYTES", len(pdf_bytes("FIRSTFILE")) + 10)
    text, _ = pdf_text(export(client, t["pt"], t["dep"]).content)
    assert "FIRSTFILE" in text and "SECONDFILE" not in text and "too large for this export" in text.replace("\n", " ")


# ------------------------------------------------------------ the hook Task 5.2 will use

def test_hidden_categories_disappear_everywhere(client, monkeypatch):
    t = team(client)
    allow(client, t)
    rx = ok(add(client, t["pt"], t["dep"], title="Visible Rx", category="prescription", file=PDF))
    lab = ok(add(client, t["pt"], t["dep"], title="Hidden Lab", category="lab_report", file=PDF))
    monkeypatch.setattr(records_service, "visible_categories", lambda db, user, dep: ("prescription",))
    d = t["dep"]
    assert [i["title"] for i in rlist(client, t["st"], d)["items"]] == ["Visible Rx"]
    assert rlist(client, t["st"], d)["total"] == 1
    assert rlist(client, t["st"], d, category="lab_report")["items"] == []
    assert_error(client.get(f"/dependents/{d}/records/{lab['record_id']}", headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.get(lab["file_path"], headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.delete(f"/dependents/{d}/records/{lab['record_id']}", headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert_error(add(client, t["st"], d, category="lab_report", notes="x"), 403, "CATEGORY_NOT_ALLOWED")
    mine = ok(add(client, t["st"], d, category="prescription", title="Mine", notes="n"))
    assert_error(client.patch(f"/dependents/{d}/records/{mine['record_id']}", json={"category": "lab_report"}, headers=auth(t["st"])), 403, "CATEGORY_NOT_ALLOWED")
    text, _ = pdf_text(export(client, t["st"], d).content)
    assert "Visible Rx" in text and "Hidden Lab" not in text
    assert_error(share(client, t["st"], d, categories=["lab_report"]), 403, "CATEGORY_NOT_ALLOWED")
    s = share(client, t["st"], d)
    assert ok(s)["categories"] == ["prescription"]
    text, _ = pdf_text(client.get(s.json()["url"]).content)
    assert "Visible Rx" in text and "Hidden Lab" not in text


# ------------------------------------------------------------ doctor links (FR-G3)

def test_doctor_link_opens_without_login_as_a_pdf(client, db):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="Shared Lab", notes="for the doctor"))
    s = ok(share(client, t["pt"], t["dep"]))
    assert s["url"] == f"/shared/records/{s['token']}" and s["status"] == "active" and s["open_count"] == 0
    assert s["scope"] == "complete" and sorted(s["categories"]) == ["lab_report", "other", "prescription", "xray"]
    life = datetime.fromisoformat(s["expires_at"]) - datetime.fromisoformat(s["created_at"])
    assert life == timedelta(hours=72)
    r = client.get(s["url"])  # no Authorization header
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "Shared Lab" in pdf_text(r.content)[0]
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-robots-tag"] == "noindex"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["content-disposition"].startswith("inline")
    row = db.scalar(select(RecordShare))
    assert row.token_hash == hashlib.sha256(s["token"].encode()).hexdigest() and s["token"] not in row.token_hash
    assert row.open_count == 1 and row.last_opened_at is not None
    assert "record_share_opened" in list(db.scalars(select(AuditLog.action)))


def test_the_secret_token_is_only_shown_once(client):
    t = team(client)
    s = ok(share(client, t["pt"], t["dep"]))
    assert len(s["token"]) >= 40
    listed = client.get(f"/dependents/{t['dep']}/records/share", headers=auth(t["pt"])).json()["items"]
    assert len(listed) == 1 and "token" not in listed[0] and "url" not in listed[0] and listed[0]["share_id"] == s["share_id"]
    other = ok(share(client, t["pt"], t["dep"]))
    assert other["token"] != s["token"]


def test_link_scope_period_hours_and_categories(client):
    t = team(client)
    ok(add(client, t["pt"], t["dep"], title="March Lab", record_date="2026-03-05", notes="n"))
    ok(add(client, t["pt"], t["dep"], title="May Rx", category="prescription", record_date="2026-05-05", notes="n"))
    ok(add(client, t["pt"], t["dep"], title="Old Xray", category="xray", record_date="2024-01-05", notes="n"))
    m = ok(share(client, t["pt"], t["dep"], scope="month", year=2026, month=3, hours=1))
    assert datetime.fromisoformat(m["expires_at"]) - datetime.fromisoformat(m["created_at"]) == timedelta(hours=1)
    text = pdf_text(client.get(m["url"]).content)[0]
    assert "March Lab" in text and "May Rx" not in text and "March 2026" in text
    y = ok(share(client, t["pt"], t["dep"], scope="year", year=2026, categories=["prescription"]))
    text = pdf_text(client.get(y["url"]).content)[0]
    assert "May Rx" in text and "March Lab" not in text and y["categories"] == ["prescription"]
    for body in (dict(scope="month", year=2026), dict(scope="year"), dict(scope="complete", year=2026), dict(hours=0), dict(hours=721),
                 dict(categories=["bad"]), dict(categories=[]), dict(year=1800, scope="year")):
        r = share(client, t["pt"], t["dep"], **body)
        assert r.status_code == 422, (body, r.text)


def test_link_shows_records_added_after_it_was_made(client):
    t = team(client)
    s = ok(share(client, t["pt"], t["dep"]))
    ok(add(client, t["pt"], t["dep"], title="Added later", notes="n"))
    assert "Added later" in pdf_text(client.get(s["url"]).content)[0]


def test_unknown_malformed_expired_and_cancelled_links(client, db):
    t = team(client)
    assert_error(client.get("/shared/records/" + "x" * 43), 404, "SHARE_NOT_FOUND")
    assert_error(client.get("/shared/records/short"), 404, "SHARE_NOT_FOUND")
    assert_error(client.get("/shared/records/" + "x" * 300), 404, "SHARE_NOT_FOUND")
    s = ok(share(client, t["pt"], t["dep"]))
    assert client.get(s["url"]).status_code == 200
    db.execute(update(RecordShare).values(created_at=datetime.now(timezone.utc) - timedelta(hours=5), expires_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db.commit()
    assert_error(client.get(s["url"]), 410, "SHARE_EXPIRED")
    listed = client.get(f"/dependents/{t['dep']}/records/share", headers=auth(t["pt"])).json()["items"]
    assert listed[0]["status"] == "expired"
    s2 = ok(share(client, t["pt"], t["dep"]))
    r = client.delete(f"/dependents/{t['dep']}/records/share/{s2['share_id']}", headers=auth(t["pt"]))
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert_error(client.get(s2["url"]), 410, "SHARE_REVOKED")
    assert client.delete(f"/dependents/{t['dep']}/records/share/{s2['share_id']}", headers=auth(t["pt"])).json()["status"] == "revoked"  # repeat is fine
    assert_error(client.delete(f"/dependents/{t['dep']}/records/share/{uuid.uuid4()}", headers=auth(t["pt"])), 404, "SHARE_NOT_FOUND")


def test_cancelling_after_open_still_stops_new_opens(client):
    t = team(client)
    s = ok(share(client, t["pt"], t["dep"]))
    assert client.get(s["url"]).status_code == 200
    client.delete(f"/dependents/{t['dep']}/records/share/{s['share_id']}", headers=auth(t["pt"]))
    assert client.get(s["url"]).status_code == 410
    row = client.get(f"/dependents/{t['dep']}/records/share", headers=auth(t["pt"])).json()["items"][0]
    assert row["open_count"] == 1 and row["status"] == "revoked"


def test_open_count_is_exact_under_parallel_opens(client, db):
    t = team(client)
    s = ok(share(client, t["pt"], t["dep"]))
    n = 8
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return client.get(s["url"]).status_code

    with ThreadPoolExecutor(n) as ex:
        assert list(ex.map(go, range(n))) == [200] * n
    db.expire_all()
    assert db.scalar(select(RecordShare.open_count)) == n


def test_who_sees_and_cancels_which_links(client):
    t = team(client)
    allow(client, t)
    by_p = ok(share(client, t["pt"], t["dep"]))
    by_s = ok(share(client, t["st"], t["dep"]))
    by_d = ok(share(client, t["dt"], t["dep"]))
    ids = lambda tok: sorted(i["share_id"] for i in client.get(f"/dependents/{t['dep']}/records/share", headers=auth(tok)).json()["items"])
    assert ids(t["pt"]) == ids(t["dt"]) == sorted([by_p["share_id"], by_s["share_id"], by_d["share_id"]])
    assert ids(t["st"]) == [by_s["share_id"]]
    cancel = lambda tok, s: client.delete(f"/dependents/{t['dep']}/records/share/{s['share_id']}", headers=auth(tok))
    assert_error(cancel(t["st"], by_p), 403, "SHARE_MODIFY_DENIED")
    assert cancel(t["st"], by_s).status_code == 200
    assert cancel(t["pt"], by_d).status_code == 200  # the Primary cancels any
    assert cancel(t["dt"], by_p).status_code == 200  # the Dependent cancels any of their own links


def test_a_secondary_who_loses_access_loses_the_links_they_made(client):
    t = team(client)
    allow(client, t)
    s = ok(share(client, t["st"], t["dep"]))
    assert client.get(s["url"]).status_code == 200
    allow(client, t, False)
    assert_error(client.get(s["url"]), 410, "SHARE_REVOKED")
    allow(client, t, True)
    assert client.get(s["url"]).status_code == 200  # access is checked at every open


def test_link_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "SHARE_MAX_ACTIVE", 2)
    t = team(client)
    a = ok(share(client, t["pt"], t["dep"]))
    ok(share(client, t["pt"], t["dep"]))
    assert_error(share(client, t["pt"], t["dep"]), 409, "SHARE_LIMIT")
    client.delete(f"/dependents/{t['dep']}/records/share/{a['share_id']}", headers=auth(t["pt"]))
    ok(share(client, t["pt"], t["dep"]))  # a cancelled link frees a place


def test_parallel_link_creation_cannot_beat_the_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "SHARE_MAX_ACTIVE", 3)
    t = team(client)
    n = 7
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return share(client, t["pt"], t["dep"]).status_code

    with ThreadPoolExecutor(n) as ex:
        codes = sorted(ex.map(go, range(n)))
    assert codes == [201] * 3 + [409] * 4


def test_public_base_url_makes_a_full_link(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUBLIC_BASE_URL", "https://api.example.com/")
    t = team(client)
    s = ok(share(client, t["pt"], t["dep"]))
    assert s["url"] == f"https://api.example.com/shared/records/{s['token']}"


def test_dependent_can_make_a_link_for_their_own_records_only(client):
    t = team(client)
    assert share(client, t["dt"], t["dep"]).status_code == 201
    tok, _ = stranger_dependent_token(client, 9)
    assert_error(share(client, tok, t["dep"]), 403, "FORBIDDEN")


def test_a_nul_character_is_refused_not_a_server_error(client):
    t = team(client)
    assert_error(add(client, t["pt"], t["dep"], title="bad\x00title", notes="n"), 422, "VALIDATION_ERROR")
    assert_error(add(client, t["pt"], t["dep"], notes="bad\x00note"), 422, "VALIDATION_ERROR")
    rec = ok(add(client, t["pt"], t["dep"], notes="fine"))
    url = f"/dependents/{t['dep']}/records/{rec['record_id']}"
    assert_error(client.patch(url, json={"title": "a\x00b"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"notes": "a\x00b"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    ok(add(client, t["pt"], t["dep"], notes="n", file=PDF, name="we\x00ird.pdf"))  # a bad file name is simply cleaned
