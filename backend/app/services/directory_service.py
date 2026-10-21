"""
Healthcare directory and home-care provider directory (Task 6.1, FR-I1 and FR-J1), read side.

  * Content is kept by the platform (migration 0016 ships the starting entries). There is no write endpoint:
    providers have no accounts and nobody edits the directory through the app (SRS FR-J1).
  * Every signed-in user (Guardian or Dependent) may read it. It holds no personal data.
  * Hidden entries (`is_active = false`) never appear and answer 404 like a missing one.
  * "Nearby": when the app sends lat + lng, entries with a position get `distance_km` (great-circle) and the
    list is sorted nearest first. Entries WITHOUT a position (national numbers such as Edhi 115) are still
    listed, after the located ones, because they cover every location. `radius_km` keeps located entries
    inside that distance and still keeps the national ones.
  * Booking and the activity log (contact events) are Task 6.2.
"""

import uuid

from sqlalchemy import Float, and_, asc, case, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import HealthcareOrganization, HomeCareProvider
from app.schemas.directory import (
    OrganizationList, OrganizationOut, OrganizationTypes, ProviderList, ProviderOut, SpecializationCount, Specializations, TypeCount,
)

EARTH_KM = 6371.0


def _like(text_: str) -> str:
    """Turn the typed words into a safe 'contains' pattern (the % and _ the user typed are plain letters)."""
    t = text_.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{t}%"


def _distance_km(lat: float, lng: float):
    """SQL: great-circle distance from (lat, lng) to the entry, in km (NULL when the entry has no position)."""
    la1, la2 = func.radians(lat), func.radians(HealthcareOrganization.lat)
    dphi = la2 - la1
    dlmb = func.radians(HealthcareOrganization.lng - lng)
    a = func.power(func.sin(dphi / 2), 2) + func.cos(la1) * func.cos(la2) * func.power(func.sin(dlmb / 2), 2)
    # LEAST() ignores NULL in PostgreSQL, so an entry without a position must be turned into NULL explicitly.
    return case((HealthcareOrganization.lat.is_(None), None), else_=2 * EARTH_KM * func.asin(func.least(1.0, func.sqrt(a))))


def list_organizations(
    db: Session, *, q: str | None, type_: str | None, city: str | None, open_24h: bool | None,
    lat: float | None, lng: float | None, radius_km: float | None, limit: int, offset: int,
) -> OrganizationList:
    if (lat is None) != (lng is None):
        raise AppError(422, "VALIDATION_ERROR", "Send lat and lng together, or neither.")
    if radius_km is not None and lat is None:
        raise AppError(422, "VALIDATION_ERROR", "radius_km needs lat and lng.")

    O = HealthcareOrganization
    where = [O.is_active.is_(True)]
    if type_:
        where.append(O.type == type_)
    if city:
        where.append(func.lower(O.city) == city.strip().lower())
    if open_24h is not None:
        where.append(O.open_24h.is_(open_24h))
    if q and q.strip():
        pat = _like(q)
        where.append(or_(O.name.ilike(pat, escape="\\"), O.city.ilike(pat, escape="\\"), O.address.ilike(pat, escape="\\"), O.services.ilike(pat, escape="\\"), O.type.ilike(pat, escape="\\")))

    if lat is not None:
        dist = _distance_km(lat, lng)
        if radius_km is not None:
            where.append(or_(O.lat.is_(None), dist <= radius_km))
        order = [asc(dist).nulls_last(), asc(O.name)]
        cols = (O, cast(dist, Float).label("distance_km"))
    else:
        order = [asc(O.name), asc(O.city)]
        cols = (O, cast(None, Float).label("distance_km"))

    total = db.scalar(select(func.count()).select_from(O).where(and_(*where))) or 0
    rows = db.execute(select(*cols).where(and_(*where)).order_by(*order, asc(O.org_id)).limit(limit).offset(offset)).all()
    items = []
    for org, d in rows:
        out = OrganizationOut.model_validate(org, from_attributes=True)
        out.distance_km = round(d, 2) if d is not None else None
        items.append(out)
    return OrganizationList(items=items, total=total, limit=limit, offset=offset)


def get_organization(db: Session, org_id: uuid.UUID) -> OrganizationOut:
    org = db.get(HealthcareOrganization, org_id)
    if org is None or not org.is_active:
        raise AppError(404, "NOT_FOUND", "Organization not found.")
    return OrganizationOut.model_validate(org, from_attributes=True)


def organization_types(db: Session) -> OrganizationTypes:
    O = HealthcareOrganization
    rows = db.execute(select(O.type, func.count()).where(O.is_active.is_(True)).group_by(O.type).order_by(O.type)).all()
    return OrganizationTypes(types=[TypeCount(type=t, count=c) for t, c in rows])


SORTS = {
    "name": lambda P: [asc(P.name)],
    "charge_asc": lambda P: [asc(P.service_charge).nulls_last(), asc(P.name)],
    "charge_desc": lambda P: [desc(P.service_charge).nulls_last(), asc(P.name)],
    "experience": lambda P: [desc(P.experience_years).nulls_last(), asc(P.name)],
}


def list_providers(
    db: Session, *, q: str | None, specialization: str | None, city: str | None,
    min_charge: float | None, max_charge: float | None, sort: str, limit: int, offset: int,
) -> ProviderList:
    if min_charge is not None and max_charge is not None and min_charge > max_charge:
        raise AppError(422, "VALIDATION_ERROR", "min_charge must not be more than max_charge.")
    P = HomeCareProvider
    where = [P.is_active.is_(True)]
    if specialization:
        where.append(func.lower(P.specialization) == specialization.strip().lower())
    if city:
        where.append(func.lower(P.city) == city.strip().lower())
    if min_charge is not None:
        where.append(P.service_charge >= min_charge)
    if max_charge is not None:
        where.append(P.service_charge <= max_charge)
    if q and q.strip():
        pat = _like(q)
        where.append(or_(P.name.ilike(pat, escape="\\"), P.specialization.ilike(pat, escape="\\"), P.city.ilike(pat, escape="\\"), P.bio.ilike(pat, escape="\\")))
    total = db.scalar(select(func.count()).select_from(P).where(and_(*where))) or 0
    rows = db.scalars(select(P).where(and_(*where)).order_by(*SORTS[sort](P), asc(P.provider_id)).limit(limit).offset(offset)).all()
    return ProviderList(items=[ProviderOut.model_validate(r, from_attributes=True) for r in rows], total=total, limit=limit, offset=offset)


def get_provider(db: Session, provider_id: uuid.UUID) -> ProviderOut:
    p = db.get(HomeCareProvider, provider_id)
    if p is None or not p.is_active:
        raise AppError(404, "NOT_FOUND", "Provider not found.")
    return ProviderOut.model_validate(p, from_attributes=True)


def specializations(db: Session) -> Specializations:
    P = HomeCareProvider
    rows = db.execute(select(P.specialization, func.count()).where(P.is_active.is_(True)).group_by(P.specialization).order_by(P.specialization)).all()
    return Specializations(specializations=[SpecializationCount(specialization=s, count=c) for s, c in rows])
