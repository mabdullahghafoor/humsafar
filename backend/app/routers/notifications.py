"""
Notifications router (Task 3.1, FR-M1 / FR-M2).

GET    /notifications                       my notifications (newest first), filters, unacknowledged-critical count
POST   /notifications/{id}/acknowledge      mark one as opened/acknowledged (idempotent)
PUT    /devices/push-token                  register this phone's Firebase token
DELETE /devices/push-token?token=...        forget it (on logout)

Any signed-in account (Guardian or Dependent) uses these for its OWN notifications only.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.notification import NotificationList, NotificationOut, PushTokenIn, PushTokenOut
from app.services import notification_service

router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=NotificationList)
def my_notifications(
    priority: Literal["standard", "critical"] | None = Query(default=None),
    unacknowledged: bool = Query(default=False, description="Only the ones not acknowledged yet."),
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None, description="Paging: the `next_before` of the previous page."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return notification_service.list_for_user(db, user, priority=priority, unacknowledged=unacknowledged, limit=limit, before=before)


@router.post("/notifications/{notification_id}/acknowledge", response_model=NotificationOut)
def acknowledge(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Call when the person opens the alert and taps Acknowledge / I'm on it."""
    return notification_service.acknowledge(db, user, notification_id)


@router.put("/devices/push-token", response_model=PushTokenOut)
def register_token(body: PushTokenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Call after login and whenever Firebase gives the app a new token."""
    notification_service.register_push_token(db, user, body.token, body.platform)
    return PushTokenOut()


@router.delete("/devices/push-token", response_model=PushTokenOut)
def unregister_token(
    token: str = Query(min_length=20, max_length=4096), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Call on logout so the next person on this phone does not get your alerts."""
    notification_service.unregister_push_token(db, user, token)
    return PushTokenOut(registered=False)
