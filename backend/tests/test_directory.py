"""
Task 6.1 tests: healthcare directory + home-care provider directory (FR-I1, FR-J1), read side.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.geo import haversine_m
from app.models import HealthcareOrganization as Org, HomeCareProvider as Prov
from app.seed.directory_data import ORGANIZATIONS, PROVIDERS
from tests.test_linkage import assert_error, auth
from tests.test_location import team

ORG_ARGS = ("name", "type", "phone", "lat", "lng", "address", "city", "services", "open_24h", "is_sample")


def add_org(db, name, type="hospital", lat=None, lng=None, city="Lahore", **kw):
    o = Org(name=name, type=type, lat=lat, lng=lng, city=city, phone=kw.pop("phone", "111"), **kw)
    db.add(o)
    db.commit()
    return o


def add_prov(db, name, spec="nurse", charge=None, city="Lahore", contact=None, **kw):
    p = Prov(name=name, specialization=spec, service_charge=charge, city=city, contact=contact or f"03{abs(hash(name)) % 10**9:09d}", **kw)
    db.add(p)
    db.commit()
    return p


def get(client, token, path, **params):
    return client.get(path, params=params, headers=auth(token) if token else {})


def names(resp):
    assert resp.status_code == 200, resp.text
    return [i["name"] for i in resp.json()["items"]]


@pytest.fixture()
def tk(client):
    t = team(client)
    return t["pt"]


# ---------------- access ----------------

ENDPOINTS = [
    "/directory/organizations", "/directory/organizations/types", "/directory/providers", "/directory/providers/specializations",
    "/directory/organizations/00000000-0000-0000-0000-000000000001", "/directory/providers/00000000-0000-0000-0000-000000000001",
]


def test_every_endpoint_needs_login(client):
    for path in ENDPOINTS:
        assert_error(get(client, None, path), 401, "NOT_AUTHENTICATED")


def test_guardian_and_dependent_can_both_read(client, db):
    t = team(client)
    add_org(db, "A Hospital")
    add_prov(db, "A Nurse")
    for token in (t["pt"], t["dt"], t["st"]):
        assert names(get(client, token, "/directory/organizations")) == ["A Hospital"]
        assert names(get(client, token, "/directory/providers")) == ["A Nurse"]


# ---------------- organizations: list, search, filters ----------------

def test_list_fields_and_default_order_by_name(client, db, tk):
    add_org(db, "Zed Clinic", "clinic", address="Road 1", services="Check-up", open_24h=True)
    add_org(db, "Alpha Hospital")
    r = get(client, tk, "/directory/organizations")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["limit"] == 20 and body["offset"] == 0
    assert [i["name"] for i in body["items"]] == ["Alpha Hospital", "Zed Clinic"]
    z = body["items"][1]
    assert z["type"] == "clinic" and z["address"] == "Road 1" and z["services"] == "Check-up" and z["open_24h"] is True
    assert z["is_sample"] is False and z["distance_km"] is None and z["city"] == "Lahore"


def test_hidden_entries_are_not_listed_counted_or_readable(client, db, tk):
    add_org(db, "Shown")
    hidden = add_org(db, "Hidden", is_active=False)
    r = get(client, tk, "/directory/organizations")
    assert names(r) == ["Shown"] and r.json()["total"] == 1
    assert_error(get(client, tk, f"/directory/organizations/{hidden.org_id}"), 404, "NOT_FOUND")
    assert get(client, tk, "/directory/organizations/types").json()["types"] == [{"type": "hospital", "count": 1}]


def test_search_text_is_case_insensitive_and_covers_name_city_services(client, db, tk):
    add_org(db, "Rose Clinic", "clinic", city="Karachi", services="Dialysis and vaccination", address="Clifton")
    add_org(db, "Other Place", city="Lahore", services="Surgery")
    assert names(get(client, tk, "/directory/organizations", q="rose")) == ["Rose Clinic"]
    assert names(get(client, tk, "/directory/organizations", q="KARACHI")) == ["Rose Clinic"]
    assert names(get(client, tk, "/directory/organizations", q="dialysis")) == ["Rose Clinic"]
    assert names(get(client, tk, "/directory/organizations", q="clifton")) == ["Rose Clinic"]
    assert names(get(client, tk, "/directory/organizations", q="nothing-like-this")) == []
    assert names(get(client, tk, "/directory/organizations", q="   ")) == ["Other Place", "Rose Clinic"]


def test_search_wildcards_typed_by_the_user_are_plain_letters(client, db, tk):
    add_org(db, "Plain Hospital")
    add_org(db, "Fifty% Pharmacy", "pharmacy")
    add_org(db, "Under_score Lab", "laboratory")
    assert names(get(client, tk, "/directory/organizations", q="%")) == ["Fifty% Pharmacy"]
    assert names(get(client, tk, "/directory/organizations", q="_")) == ["Under_score Lab"]
    assert names(get(client, tk, "/directory/organizations", q="\\")) == []


def test_search_text_cannot_inject_sql(client, db, tk):
    add_org(db, "Safe Hospital")
    r = get(client, tk, "/directory/organizations", q="'; DROP TABLE healthcare_organizations; --")
    assert r.status_code == 200 and r.json()["items"] == []
    assert names(get(client, tk, "/directory/organizations")) == ["Safe Hospital"]


def test_filters_type_city_open_24h(client, db, tk):
    add_org(db, "H1", "hospital", city="Lahore", open_24h=True)
    add_org(db, "P1", "pharmacy", city="Lahore")
    add_org(db, "H2", "hospital", city="Karachi")
    assert names(get(client, tk, "/directory/organizations", type="hospital")) == ["H1", "H2"]
    assert names(get(client, tk, "/directory/organizations", city="lahore")) == ["H1", "P1"]
    assert names(get(client, tk, "/directory/organizations", open_24h="true")) == ["H1"]
    assert names(get(client, tk, "/directory/organizations", open_24h="false")) == ["H2", "P1"]
    assert names(get(client, tk, "/directory/organizations", type="hospital", city="Karachi")) == ["H2"]
    assert_error(get(client, tk, "/directory/organizations", type="spaceship"), 422, "VALIDATION_ERROR")


def test_paging_is_stable_and_total_is_the_full_count(client, db, tk):
    for i in range(5):
        add_org(db, f"Org {i}")
    p1 = get(client, tk, "/directory/organizations", limit=2, offset=0).json()
    p2 = get(client, tk, "/directory/organizations", limit=2, offset=2).json()
    p3 = get(client, tk, "/directory/organizations", limit=2, offset=4).json()
    assert p1["total"] == p2["total"] == p3["total"] == 5
    assert [i["name"] for i in p1["items"] + p2["items"] + p3["items"]] == [f"Org {i}" for i in range(5)]
    assert get(client, tk, "/directory/organizations", offset=99).json()["items"] == []
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert_error(get(client, tk, "/directory/organizations", **bad), 422, "VALIDATION_ERROR")


def test_one_organization_and_bad_ids(client, db, tk):
    o = add_org(db, "Solo", phone="115")
    r = get(client, tk, f"/directory/organizations/{o.org_id}")
    assert r.status_code == 200 and r.json()["name"] == "Solo" and r.json()["phone"] == "115"
    assert_error(get(client, tk, "/directory/organizations/00000000-0000-0000-0000-000000000009"), 404, "NOT_FOUND")
    assert_error(get(client, tk, "/directory/organizations/not-a-uuid"), 422, "VALIDATION_ERROR")


def test_types_endpoint_counts_and_is_not_taken_for_an_id(client, db, tk):
    add_org(db, "H1", "hospital")
    add_org(db, "H2", "hospital", city="Karachi")
    add_org(db, "A1", "ambulance", city="Nationwide")
    r = get(client, tk, "/directory/organizations/types")
    assert r.status_code == 200
    assert r.json() == {"types": [{"type": "ambulance", "count": 1}, {"type": "hospital", "count": 2}]}


# ---------------- organizations: nearby ----------------

def three_places(db):
    add_org(db, "Here", lat=31.0, lng=74.0)
    add_org(db, "Eleven km", lat=31.1, lng=74.0)
    add_org(db, "Fifty-five km", lat=31.5, lng=74.0)
    add_org(db, "National line", "ambulance", city="Nationwide", phone="115")


def test_nearby_sorts_nearest_first_and_national_numbers_come_last(client, db, tk):
    three_places(db)
    r = get(client, tk, "/directory/organizations", lat=31.0, lng=74.0)
    assert names(r) == ["Here", "Eleven km", "Fifty-five km", "National line"]
    d = [i["distance_km"] for i in r.json()["items"]]
    assert d[0] == 0.0 and d[1] == pytest.approx(11.12, abs=0.05) and d[2] == pytest.approx(55.6, abs=0.1) and d[3] is None


def test_nearby_from_another_point_changes_the_order(client, db, tk):
    three_places(db)
    assert names(get(client, tk, "/directory/organizations", lat=31.5, lng=74.0)) == ["Fifty-five km", "Eleven km", "Here", "National line"]


def test_radius_drops_far_entries_but_keeps_national_numbers(client, db, tk):
    three_places(db)
    assert names(get(client, tk, "/directory/organizations", lat=31.0, lng=74.0, radius_km=20)) == ["Here", "Eleven km", "National line"]
    r = get(client, tk, "/directory/organizations", lat=31.0, lng=74.0, radius_km=1)
    assert names(r) == ["Here", "National line"] and r.json()["total"] == 2


def test_distance_agrees_with_the_geofence_distance_function(client, db, tk):
    add_org(db, "Karachi Spot", lat=24.8607, lng=67.0011)
    r = get(client, tk, "/directory/organizations", lat=31.5497, lng=74.3436)
    want = haversine_m(31.5497, 74.3436, 24.8607, 67.0011) / 1000
    assert r.json()["items"][0]["distance_km"] == pytest.approx(want, abs=0.02)


def test_nearby_filters_still_apply_and_extreme_points_do_not_crash(client, db, tk):
    three_places(db)
    add_org(db, "Pharmacy Near", "pharmacy", lat=31.01, lng=74.0)
    assert names(get(client, tk, "/directory/organizations", lat=31.0, lng=74.0, type="pharmacy")) == ["Pharmacy Near"]
    for lat, lng in ((90, 0), (-90, 180), (0, -180)):
        assert get(client, tk, "/directory/organizations", lat=lat, lng=lng).status_code == 200


def test_bad_location_input_is_rejected(client, db, tk):
    for params in ({"lat": 31.0}, {"lng": 74.0}, {"radius_km": 5}, {"lat": 91, "lng": 0}, {"lat": 0, "lng": 181},
                   {"lat": 31, "lng": 74, "radius_km": 0}, {"lat": 31, "lng": 74, "radius_km": -3}, {"lat": "x", "lng": 1}):
        assert_error(get(client, tk, "/directory/organizations", **params), 422, "VALIDATION_ERROR")


# ---------------- providers ----------------

def test_provider_list_and_one_provider(client, db, tk):
    p = add_prov(db, "Nurse A", "nurse", 2500, bio="Home nursing", experience_years=8, charge_unit="per_visit", contact="0300-1")
    r = get(client, tk, "/directory/providers")
    item = r.json()["items"][0]
    assert r.json()["total"] == 1 and item["name"] == "Nurse A" and item["service_charge"] == 2500.0
    assert item["charge_unit"] == "per_visit" and item["contact"] == "0300-1" and item["bio"] == "Home nursing"
    assert item["experience_years"] == 8 and item["is_sample"] is False
    one = get(client, tk, f"/directory/providers/{p.provider_id}")
    assert one.status_code == 200 and one.json() == item
    assert_error(get(client, tk, "/directory/providers/00000000-0000-0000-0000-000000000009"), 404, "NOT_FOUND")
    assert_error(get(client, tk, "/directory/providers/nope"), 422, "VALIDATION_ERROR")


def test_provider_filters_and_search(client, db, tk):
    add_prov(db, "Ayesha", "nurse", 2500, city="Lahore", bio="Wound dressing")
    add_prov(db, "Imran", "physiotherapist", 3500, city="Islamabad")
    add_prov(db, "Hina", "nurse", 3000, city="Karachi")
    add_prov(db, "Free Advice", "attendant", None, city="Lahore")
    assert names(get(client, tk, "/directory/providers", specialization="NURSE")) == ["Ayesha", "Hina"]
    assert names(get(client, tk, "/directory/providers", city="lahore")) == ["Ayesha", "Free Advice"]
    assert names(get(client, tk, "/directory/providers", max_charge=3000)) == ["Ayesha", "Hina"]
    assert names(get(client, tk, "/directory/providers", min_charge=3000)) == ["Hina", "Imran"]
    assert names(get(client, tk, "/directory/providers", min_charge=3000, max_charge=3000)) == ["Hina"]
    assert names(get(client, tk, "/directory/providers", q="dressing")) == ["Ayesha"]
    assert names(get(client, tk, "/directory/providers", q="PHYSIO")) == ["Imran"]
    assert names(get(client, tk, "/directory/providers", specialization="nurse", city="Karachi", max_charge=5000)) == ["Hina"]
    assert_error(get(client, tk, "/directory/providers", min_charge=10, max_charge=5), 422, "VALIDATION_ERROR")
    assert_error(get(client, tk, "/directory/providers", min_charge=-1), 422, "VALIDATION_ERROR")


def test_provider_sorting_puts_unknown_charge_last(client, db, tk):
    add_prov(db, "Cheap", charge=1000, experience_years=2)
    add_prov(db, "Dear", charge=5000, experience_years=20)
    add_prov(db, "Unknown", charge=None, experience_years=None)
    assert names(get(client, tk, "/directory/providers", sort="name")) == ["Cheap", "Dear", "Unknown"]
    assert names(get(client, tk, "/directory/providers", sort="charge_asc")) == ["Cheap", "Dear", "Unknown"]
    assert names(get(client, tk, "/directory/providers", sort="charge_desc")) == ["Dear", "Cheap", "Unknown"]
    assert names(get(client, tk, "/directory/providers", sort="experience")) == ["Dear", "Cheap", "Unknown"]
    assert_error(get(client, tk, "/directory/providers", sort="random"), 422, "VALIDATION_ERROR")


def test_hidden_providers_and_specializations_endpoint(client, db, tk):
    add_prov(db, "N1", "nurse")
    add_prov(db, "N2", "nurse")
    add_prov(db, "P1", "physiotherapist")
    hidden = add_prov(db, "Gone", "attendant", is_active=False)
    assert names(get(client, tk, "/directory/providers")) == ["Gone"][:0] + ["N1", "N2", "P1"]
    assert_error(get(client, tk, f"/directory/providers/{hidden.provider_id}"), 404, "NOT_FOUND")
    r = get(client, tk, "/directory/providers/specializations")
    assert r.status_code == 200
    assert r.json() == {"specializations": [{"specialization": "nurse", "count": 2}, {"specialization": "physiotherapist", "count": 1}]}


def test_provider_paging(client, db, tk):
    for i in range(5):
        add_prov(db, f"P {i}")
    got = []
    for off in (0, 2, 4):
        r = get(client, tk, "/directory/providers", limit=2, offset=off).json()
        assert r["total"] == 5
        got += [i["name"] for i in r["items"]]
    assert got == [f"P {i}" for i in range(5)]


# ---------------- database rules and the starting content ----------------

def test_database_rejects_bad_directory_rows(db):
    bad_orgs = [
        dict(name="X", type="spaceship", city="C"),
        dict(name="X", type="hospital", city="C", lat=10.0, lng=None),
        dict(name="X", type="hospital", city="C", lat=None, lng=10.0),
        dict(name="X", type="hospital", city="C", lat=91.0, lng=0.0),
        dict(name="X", type="hospital", city="C", lat=0.0, lng=181.0),
        dict(name="   ", type="hospital", city="C"),
    ]
    for kw in bad_orgs:
        db.add(Org(**kw))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    bad_provs = [
        dict(service_charge=-1), dict(experience_years=71), dict(experience_years=-1), dict(charge_unit="per_year"), dict(name="  "),
    ]
    for kw in bad_provs:
        base = dict(name="P", specialization="nurse", contact="1", city="C")
        base.update(kw)
        db.add(Prov(**base))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_same_name_in_the_same_city_is_one_entry(db):
    add_org(db, "Twin", city="Lahore")
    add_org(db, "Twin", city="Karachi")  # another city is fine
    db.add(Org(name="Twin", type="clinic", city="Lahore"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    add_prov(db, "Same", contact="1")
    add_prov(db, "Same", contact="2")
    db.add(Prov(name="Same", specialization="nurse", contact="1", city="X"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_starting_content_is_valid_and_has_the_real_emergency_numbers(db, client, tk):
    for row in ORGANIZATIONS:
        db.add(Org(**dict(zip(ORG_ARGS, row))))
    for name, spec, charge, unit, contact, bio, city, years, sample in PROVIDERS:
        db.add(Prov(name=name, specialization=spec, service_charge=charge, charge_unit=unit, contact=contact, bio=bio, city=city, experience_years=years, is_sample=sample))
    db.commit()
    real = {o.name: o for o in db.query(Org).filter(Org.is_sample.is_(False))}
    assert {o.phone for o in real.values()} == {"115", "1020", "1021", "1122", "15", "16"}
    assert real["Edhi Foundation Ambulance"].phone == "115" and real["Chhipa Welfare Ambulance"].phone == "1020"
    assert all(o.lat is None and o.city == "Nationwide" and o.open_24h for o in real.values())
    assert all(o.is_sample for o in db.query(Org).filter(Org.lat.isnot(None)))
    assert all(p.is_sample for p in db.query(Prov))
    # nearby from Lahore: the Lahore demo hospital comes first, the national numbers last
    r = get(client, tk, "/directory/organizations", lat=31.55, lng=74.34, limit=100).json()
    assert r["total"] == len(ORGANIZATIONS) and r["items"][0]["name"] == "Demo City General Hospital"
    assert all(i["distance_km"] is None for i in r["items"][-6:])
    types = {t["type"] for t in get(client, tk, "/directory/organizations/types").json()["types"]}
    assert {"hospital", "clinic", "pharmacy", "ambulance", "emergency_service"} <= types
    assert len(get(client, tk, "/directory/providers/specializations").json()["specializations"]) >= 4
