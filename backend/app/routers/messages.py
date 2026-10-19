"""
Text messaging router (Task 4.2, FR-E1).

POST /messages                 send a text message to a linked person
GET  /messages                 history with one person (newest first, paged with `before`)
GET  /messages/conversations   my conversations, with last message and unread count
POST /messages/read            mark everything from one person as read
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.message import ConversationList, MessageIn, MessageList, MessageOut, ReadIn, ReadOut
from app.services import messaging_service as svc

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", response_model=MessageOut, status_code=201)
def send_message(body: MessageIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = svc.send(db, user, body)
    if out.already_sent:
        response.status_code = 200
    return out


@router.get("/conversations", response_model=ConversationList)
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.conversations(db, user)


@router.get("", response_model=MessageList)
def get_history(
    with_user_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=100),
    before: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.history(db, user, with_user_id, limit=limit, before=before)


@router.post("/read", response_model=ReadOut)
def read_messages(body: ReadIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.mark_read(db, user, body)
