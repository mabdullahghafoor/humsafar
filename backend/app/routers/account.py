"""
Account closure router (Task 6.7, FR-O1).

POST /account/close                    a Guardian closes their own account (password)
POST /account/reopen                   public: get a closed Guardian account back within the period (email + password)
POST /dependents/{id}/close            the Primary Guardian closes the Dependent's account (Primary's password)
POST /dependents/{id}/reopen           the Primary Guardian reopens it within the period
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ratelimit import per_ip
from app.models import User
from app.schemas.account import ClosureOut, PasswordIn, ReopenIn
from app.services import account_service as svc

router = APIRouter(tags=["Account closure"])


@router.post("/account/close", response_model=ClosureOut)
def close_account(body: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.close_guardian(db, user, body.password)


@router.post("/account/reopen", dependencies=[Depends(per_ip("login", "RATE_LOGIN_PER_MIN"))])
def reopen_account(body: ReopenIn, db: Session = Depends(get_db)):
    return svc.reopen_guardian(db, str(body.email), body.password)


@router.post("/dependents/{dependent_id}/close", response_model=ClosureOut)
def close_dependent(dependent_id: uuid.UUID, body: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.close_dependent(db, user, dependent_id, body.password)


@router.post("/dependents/{dependent_id}/reopen", response_model=ClosureOut)
def reopen_dependent(dependent_id: uuid.UUID, body: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.reopen_dependent(db, user, dependent_id, body.password)
