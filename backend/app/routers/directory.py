"""
Healthcare directory and home-care provider directory router (Task 6.1, FR-I1 and FR-J1). Read only.

GET /directory/organizations             search and list (q, type, city, open_24h, lat+lng, radius_km; paged)
GET /directory/organizations/types       the types that exist, with counts
GET /directory/organizations/{org_id}    one organization
GET /directory/providers                 search and list (q, specialization, city, min/max_charge, sort; paged)
GET /directory/providers/specializations the specializations that exist, with counts
GET /directory/providers/{provider_id}   one provider
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.directory import OrganizationList, OrganizationOut, OrganizationTypes, OrgType, ProviderList, ProviderOut, Specializations
from app.services import directory_service as svc

router = APIRouter(prefix="/directory", tags=["Directory"])


@router.get("/organizations", response_model=OrganizationList)
def organizations(
    q: str | None = Query(None, max_length=100, description="Words to find in the name, city, address, services or type."),
    type: OrgType | None = Query(None),
    city: str | None = Query(None, max_length=80),
    open_24h: bool | None = Query(None),
    lat: float | None = Query(None, ge=-90, le=90, description="Your latitude (Guardian's or Dependent's). Send with lng for 'nearby'."),
    lng: float | None = Query(None, ge=-180, le=180),
    radius_km: float | None = Query(None, gt=0, le=1000, description="Only with lat and lng. National numbers (no position) are always kept."),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_organizations(db, q=q, type_=type, city=city, open_24h=open_24h, lat=lat, lng=lng, radius_km=radius_km, limit=limit, offset=offset)


@router.get("/organizations/types", response_model=OrganizationTypes)
def organization_types(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.organization_types(db)


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
def organization(org_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_organization(db, org_id)


@router.get("/providers", response_model=ProviderList)
def providers(
    q: str | None = Query(None, max_length=100, description="Words to find in the name, specialization, city or profile."),
    specialization: str | None = Query(None, max_length=100),
    city: str | None = Query(None, max_length=80),
    min_charge: float | None = Query(None, ge=0),
    max_charge: float | None = Query(None, ge=0),
    sort: Literal["name", "charge_asc", "charge_desc", "experience"] = Query("name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.list_providers(db, q=q, specialization=specialization, city=city, min_charge=min_charge, max_charge=max_charge, sort=sort, limit=limit, offset=offset)


@router.get("/providers/specializations", response_model=Specializations)
def specializations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.specializations(db)


@router.get("/providers/{provider_id}", response_model=ProviderOut)
def provider(provider_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_provider(db, provider_id)
