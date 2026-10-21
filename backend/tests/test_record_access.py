"""
Task 5.2 tests: field-level access control on medical records (FR-G2).
The Primary hides single record categories from a Secondary Guardian; everything in the vault respects it.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.models import AuditLog, RecordCategoryRestriction
from tests.test_linkage import assert_error, auth, make_secondary
from tests.test_location import team
from tests.test_permissions import verify
from tests.test_records import add, allow, export, files_on_disk, ok, pdf_bytes, pdf_text, rlist, share, store, PDF  # noqa: F401 (store is an autouse fixture)

CATS = ["prescription", "lab_report", "xray", "other"]


def setvis(client, token, dep, category, guardian_id, visible):
    return client.put(
        f"/dependents/{dep}/records/access/{category}", json={"guardian_id": guardian_id, "visible": visible}, headers=auth(token)
    )


def dash(client, token, dep):
    r = client.get(f"/dependents/{dep}/records/access", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def mine(client, token, dep):
    r = client.get(f"/dependents/{dep}/records/access/me", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def vault(client, t):
    """One Primary-added record in every category; the Secondary may use the module. Returns {category: record}."""
    allow(client, t)
    return {c: ok(add(client, t["pt"], t["dep"], category=c, title=f"T-{c}", notes=f"n-{c}", file=PDF)) for c in CATS}


def titles(client, token, dep, **params):
    return sorted(r["title"] for r in rlist(client, token, dep, **params)["items"])


# ------------------------------------------------------------ defaults and the dashboard

def test_secondary_with_the_module_sees_every_category_by_default(client, store):
    t = team(client)
    vault(client, t)
    assert titles(client, t["st"], t["dep"]) == sorted(f"T-{c}" for c in CATS)
    me = mine(client, t["st"], t["dep"])
    assert me["visible_categories"] == CATS and all(me["categories"].values())


def test_dashboard_lists_each_secondary_with_module_and_categories(client, store):
    t = team(client)
    d = dash(client, t["pt"], t["dep"])
    assert d["categories"] == CATS and len(d["secondaries"]) == 1
    s = d["secondaries"][0]
    assert s["guardian_id"] == t["sid"] and s["health_records_granted"] is False  # module not granted yet
    assert s["categories"] == {c: True for c in CATS}
    allow(client, t)
    assert dash(client, t["pt"], t["dep"])["secondaries"][0]["health_records_granted"] is True
    assert ok(setvis(client, t["pt"], t["dep"], "xray", t["sid"], False), 200)["visible_categories"] == ["prescription", "lab_report", "other"]
    assert dash(client, t["pt"], t["dep"])["secondaries"][0]["categories"]["xray"] is False


def test_only_the_primary_may_see_the_dashboard_or_change_it(client, store):
    t = team(client)
    allow(client, t)
    assert_error(client.get(f"/dependents/{t['dep']}/records/access", headers=auth(t["st"])), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(setvis(client, t["st"], t["dep"], "xray", t["sid"], False), 403, "NOT_PRIMARY_GUARDIAN")
    assert client.get(f"/dependents/{t['dep']}/records/access", headers=auth(t["dt"])).status_code == 403  # a Dependent is not a Guardian
    assert setvis(client, t["dt"], t["dep"], "xray", t["sid"], False).status_code == 403
    assert client.get(f"/dependents/{t['dep']}/records/access").status_code == 401
    assert mine(client, t["st"], t["dep"])["visible_categories"] == CATS  # nothing changed


def test_a_stranger_primary_cannot_touch_another_dependents_setting(client, store):
    t = team(client)
    from tests.test_linkage import link, make_dependent, make_guardian
    from tests.test_linkage import PASSWORD, PHOTO
    gt, _, _ = make_guardian(client, 9)
    dep2 = make_dependent(client, 2)
    assert client.post(f"/dependents/{dep2}/kyc-verify", json={"password": PASSWORD, "cnic": "42101-7654322-1", "liveness_image": PHOTO}).status_code == 200
    assert link(client, gt, dep2).status_code == 201
    assert_error(setvis(client, gt, t["dep"], "xray", t["sid"], False), 403, "NOT_PRIMARY_GUARDIAN")
    assert_error(client.get(f"/dependents/{t['dep']}/records/access", headers=auth(gt)), 403, "NOT_PRIMARY_GUARDIAN")


def test_setting_errors(client, store):
    t = team(client)
    other_token, other_id, _ = make_secondary(client, t["pt"], t["dep"], 2)
    assert_error(setvis(client, t["pt"], t["dep"], "invoices", t["sid"], False), 422, "UNKNOWN_CATEGORY")
    assert_error(setvis(client, t["pt"], t["dep"], "xray", "00000000-0000-0000-0000-000000000001", False), 404, "SECONDARY_NOT_FOUND")
    pid = client.get("/auth/me", headers=auth(t["pt"])).json()["user_id"]
    assert_error(setvis(client, t["pt"], t["dep"], "xray", pid, False), 400, "PRIMARY_NOT_GOVERNABLE")
    assert client.put(f"/dependents/{t['dep']}/records/access/xray", json={"guardian_id": t["sid"]}, headers=auth(t["pt"])).status_code == 422
    assert client.put(f"/dependents/{t['dep']}/records/access/xray", json={"guardian_id": "nope", "visible": False}, headers=auth(t["pt"])).status_code == 422
    assert client.put(f"/dependents/{t['dep']}/records/access/xray", json={"guardian_id": t["sid"], "visible": "maybe"}, headers=auth(t["pt"])).status_code == 422
    assert db_rows(client) == 0


def db_rows(client):
    from tests.conftest import TEST_DATABASE_URL  # noqa: F401
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(TEST_DATABASE_URL)
    try:
        with sessionmaker(bind=eng)() as s:
            return s.scalar(select(func.count()).select_from(RecordCategoryRestriction))
    finally:
        eng.dispose()


# ------------------------------------------------------------ reading is filtered

def test_hidden_category_is_invisible_in_list_one_file_and_filter(client, store):
    t = team(client)
    recs = vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    got = rlist(client, t["st"], t["dep"])
    assert got["total"] == 3 and titles(client, t["st"], t["dep"]) == ["T-lab_report", "T-other", "T-prescription"]
    x = recs["xray"]
    assert_error(client.get(f"/dependents/{t['dep']}/records/{x['record_id']}", headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.get(x["file_path"], headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    # asking for the hidden category directly gives an empty list, not an error that would reveal it exists
    only = rlist(client, t["st"], t["dep"], category="xray")
    assert only["items"] == [] and only["total"] == 0
    # the Primary and the Dependent still see everything
    assert len(rlist(client, t["pt"], t["dep"])["items"]) == 4 and len(rlist(client, t["dt"], t["dep"])["items"]) == 4
    assert client.get(x["file_path"], headers=auth(t["pt"])).status_code == 200


def test_paging_counts_only_visible_records(client, store):
    t = team(client)
    vault(client, t)
    for i in range(3):
        ok(add(client, t["pt"], t["dep"], category="xray", title=f"X{i}", notes="n"))
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    p = rlist(client, t["st"], t["dep"], limit=2, offset=0)
    assert p["total"] == 3 and len(p["items"]) == 2
    assert rlist(client, t["st"], t["dep"], limit=2, offset=2)["total"] == 3


def test_showing_the_category_again_restores_it(client, store):
    t = team(client)
    vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    assert rlist(client, t["st"], t["dep"])["total"] == 3
    r = setvis(client, t["pt"], t["dep"], "xray", t["sid"], True)
    assert r.status_code == 200 and r.json()["visible"] is True
    assert rlist(client, t["st"], t["dep"])["total"] == 4 and db_rows(client) == 0


def test_changes_are_idempotent_and_audited_only_when_something_changed(client, store):
    t = team(client)
    allow(client, t)

    def n(action, db):
        return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from tests.conftest import TEST_DATABASE_URL
    eng = create_engine(TEST_DATABASE_URL)
    S = sessionmaker(bind=eng)
    try:
        for _ in range(3):
            assert setvis(client, t["pt"], t["dep"], "xray", t["sid"], False).status_code == 200
        assert setvis(client, t["pt"], t["dep"], "other", t["sid"], True).status_code == 200  # already visible: no change
        with S() as s:
            assert n("record_category_hidden", s) == 1 and n("record_category_shown", s) == 0
            assert s.scalar(select(func.count()).select_from(RecordCategoryRestriction)) == 1
        assert setvis(client, t["pt"], t["dep"], "xray", t["sid"], True).status_code == 200
        assert setvis(client, t["pt"], t["dep"], "xray", t["sid"], True).status_code == 200
        with S() as s:
            assert n("record_category_shown", s) == 1
    finally:
        eng.dispose()


# ------------------------------------------------------------ writing

def test_secondary_cannot_add_or_move_a_record_into_a_hidden_category(client, store):
    t = team(client)
    allow(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    assert_error(add(client, t["st"], t["dep"], category="xray", notes="n"), 403, "CATEGORY_NOT_ALLOWED")
    mine_rec = ok(add(client, t["st"], t["dep"], category="other", notes="n"))
    r = client.patch(f"/dependents/{t['dep']}/records/{mine_rec['record_id']}", json={"category": "xray"}, headers=auth(t["st"]))
    assert_error(r, 403, "CATEGORY_NOT_ALLOWED")
    # an allowed move still works
    r = client.patch(f"/dependents/{t['dep']}/records/{mine_rec['record_id']}", json={"category": "prescription"}, headers=auth(t["st"]))
    assert r.status_code == 200 and r.json()["category"] == "prescription"


def test_secondary_cannot_edit_or_delete_a_record_that_is_now_hidden(client, store):
    t = team(client)
    allow(client, t)
    mine_rec = ok(add(client, t["st"], t["dep"], category="xray", title="Mine", notes="n"))
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    url = f"/dependents/{t['dep']}/records/{mine_rec['record_id']}"
    assert_error(client.patch(url, json={"title": "Changed"}, headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert_error(client.delete(url, headers=auth(t["st"])), 404, "RECORD_NOT_FOUND")
    assert client.get(url, headers=auth(t["pt"])).json()["title"] == "Mine"  # the Primary still manages it


# ------------------------------------------------------------ export and doctor links

def test_export_leaves_out_hidden_categories(client, store):
    t = team(client)
    vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    r = export(client, t["st"], t["dep"], scope="complete")
    assert r.status_code == 200
    text, _ = pdf_text(r.content)
    assert "T-lab_report" in text and "T-xray" not in text
    full, _ = pdf_text(export(client, t["pt"], t["dep"], scope="complete").content)
    assert "T-xray" in full


def test_export_with_only_hidden_records_is_empty_for_the_secondary(client, store):
    t = team(client)
    allow(client, t)
    ok(add(client, t["pt"], t["dep"], category="xray", title="OnlyX", notes="n"))
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    r = export(client, t["st"], t["dep"], scope="complete")
    assert r.status_code == 200 and "OnlyX" not in pdf_text(r.content)[0]  # an empty report, never the hidden record


def test_secondary_cannot_share_a_hidden_category_and_default_link_skips_it(client, store):
    t = team(client)
    vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    assert_error(share(client, t["st"], t["dep"], scope="complete", categories=["xray"]), 403, "CATEGORY_NOT_ALLOWED")
    made = ok(share(client, t["st"], t["dep"], scope="complete"))
    assert made["categories"] == ["prescription", "lab_report", "other"]
    text, _ = pdf_text(client.get(made["url"]).content)
    assert "T-lab_report" in text and "T-xray" not in text


def test_a_category_hidden_after_the_link_was_made_disappears_from_the_link(client, store):
    t = team(client)
    vault(client, t)
    made = ok(share(client, t["st"], t["dep"], scope="complete", categories=["xray", "other"]))
    assert "T-xray" in pdf_text(client.get(made["url"]).content)[0]
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    text, _ = pdf_text(client.get(made["url"]).content)
    assert "T-xray" not in text and "T-other" in text
    setvis(client, t["pt"], t["dep"], "other", t["sid"], False)  # now nothing is left in this link
    assert_error(client.get(made["url"]), 410, "SHARE_REVOKED")
    setvis(client, t["pt"], t["dep"], "other", t["sid"], True)  # and it comes back if access is given again
    assert "T-other" in pdf_text(client.get(made["url"]).content)[0]


def test_primary_links_are_not_narrowed(client, store):
    t = team(client)
    vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    made = ok(share(client, t["pt"], t["dep"], scope="complete"))
    assert "T-xray" in pdf_text(client.get(made["url"]).content)[0]


# ------------------------------------------------------------ interplay with the module gate

def test_the_module_gate_still_comes_first(client, store):
    t = team(client)
    vault(client, t)
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    allow(client, t, False)  # module revoked
    assert_error(client.get(f"/dependents/{t['dep']}/records", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(f"/dependents/{t['dep']}/records/access/me", headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    allow(client, t, True)  # granted again: the hidden category is still hidden
    assert mine(client, t["st"], t["dep"])["visible_categories"] == ["prescription", "lab_report", "other"]


def test_hiding_every_category_leaves_an_empty_vault_not_an_error(client, store):
    t = team(client)
    vault(client, t)
    for c in CATS:
        assert setvis(client, t["pt"], t["dep"], c, t["sid"], False).status_code == 200
    empty = rlist(client, t["st"], t["dep"])
    assert empty["items"] == [] and empty["total"] == 0
    assert mine(client, t["st"], t["dep"])["visible_categories"] == []


def test_each_secondary_has_their_own_setting(client, store):
    t = team(client)
    vault(client, t)
    st2, sid2, _ = make_secondary(client, t["pt"], t["dep"], 2)
    verify(client, st2)
    assert client.put(f"/dependents/{t['dep']}/permissions/health_records", json={"guardian_id": sid2, "granted": True}, headers=auth(t["pt"])).status_code == 200
    setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)
    assert rlist(client, t["st"], t["dep"])["total"] == 3
    assert rlist(client, st2, t["dep"])["total"] == 4  # the other Secondary is unaffected
    d = {s["guardian_id"]: s["categories"] for s in dash(client, t["pt"], t["dep"])["secondaries"]}
    assert d[t["sid"]]["xray"] is False and d[sid2]["xray"] is True


def test_dependent_and_primary_always_see_all_categories(client, store):
    t = team(client)
    vault(client, t)
    for c in CATS:
        setvis(client, t["pt"], t["dep"], c, t["sid"], False)
    assert mine(client, t["pt"], t["dep"])["visible_categories"] == CATS
    assert mine(client, t["dt"], t["dep"])["visible_categories"] == CATS


def test_me_endpoint_is_closed_to_outsiders(client, store):
    t = team(client)
    from tests.test_records import stranger_dependent_token
    other_dep_token, _ = stranger_dependent_token(client, 3)
    assert client.get(f"/dependents/{t['dep']}/records/access/me", headers=auth(other_dep_token)).status_code == 403
    assert client.get(f"/dependents/{t['dep']}/records/access/me").status_code == 401


# ------------------------------------------------------------ races

def test_parallel_identical_changes_leave_exactly_one_row(client, store):
    t = team(client)
    allow(client, t)
    n = 6
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return setvis(client, t["pt"], t["dep"], "xray", t["sid"], False)

    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(go, range(n)))
    assert [r.status_code for r in res] == [200] * n, [r.text for r in res]
    assert db_rows(client) == 1


def test_parallel_hide_and_show_never_error_and_end_consistent(client, store):
    t = team(client)
    vault(client, t)
    n = 8
    gate = Barrier(n)

    def go(i):
        gate.wait()
        return setvis(client, t["pt"], t["dep"], "xray", t["sid"], i % 2 == 0)

    with ThreadPoolExecutor(n) as ex:
        res = list(ex.map(go, range(n)))
    assert all(r.status_code == 200 for r in res), [r.text for r in res]
    rows = db_rows(client)
    assert rows in (0, 1)
    seen = rlist(client, t["st"], t["dep"])["total"]
    assert seen == (3 if rows == 1 else 4)  # what the Secondary sees matches what is stored
