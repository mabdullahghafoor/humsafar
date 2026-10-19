"""
Text messaging (Task 4.2, FR-E1) between a Guardian and a linked Dependent.

Rules
- Only a Guardian <-> Dependent pair that are linked (active link). Guardian to Guardian and Dependent to Dependent: 403.
- A Primary Guardian always may. A Secondary needs the `communication` permission (same check in both directions,
  so a Secondary who loses it can no longer send, receive or read the history).
- A retry with the same `client_id` returns the first message and sends nothing new (`already_sent` = true).
- A standard notification (type `message`) is sent to the receiver, with a short preview.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Message, User
from app.schemas.message import ConversationList, ConversationOut, MessageIn, MessageList, MessageOut, ReadIn, ReadOut
from app.services import notification_service as ns
from app.services import permission_service

MODULE = "communication"
PREVIEW = 80


def _pair(db: Session, me: User, other_id: uuid.UUID) -> tuple[User, uuid.UUID]:
    """Check that `me` and `other_id` may talk. Returns (other user, dependent_id) or raises 403."""
    other = db.get(User, other_id)
    if other is None or other.user_id == me.user_id or other.role == me.role:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You can only message a person you are linked to.")
    guardian, dep_id = (me, other.user_id) if me.role == "guardian" else (other, me.user_id)
    permission_service.check_module_access(db, guardian, dep_id, MODULE)
    return other, dep_id


def _out(m: Message, me: User, *, already: bool = False) -> MessageOut:
    return MessageOut(
        message_id=m.message_id, sender_id=m.sender_id, receiver_id=m.receiver_id, type=m.type, body=m.body,
        content_url=m.content_url, priority=m.priority, sent_at=m.sent_at, read_at=m.read_at,
        from_me=m.sender_id == me.user_id, already_sent=already,
    )


def send(db: Session, me: User, data: MessageIn) -> MessageOut:
    other, dep_id = _pair(db, me, data.receiver_id)
    row = None
    if data.client_id is not None:
        stmt = (
            pg_insert(Message)
            .values(message_id=uuid.uuid4(), sender_id=me.user_id, receiver_id=other.user_id, type="text",
                    body=data.body, priority="standard", client_id=data.client_id)
            .on_conflict_do_nothing(index_elements=["sender_id", "client_id"], index_where=text("client_id IS NOT NULL"))
            .returning(Message.message_id)
        )
        new_id = db.execute(stmt).scalar()
        db.commit()
        if new_id is None:  # same client_id seen before: answer with the first message
            old = db.scalar(select(Message).where(Message.sender_id == me.user_id, Message.client_id == data.client_id))
            if old.receiver_id != other.user_id or old.body != data.body:
                raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different message.")
            return _out(old, me, already=True)
        row = db.get(Message, new_id)
    else:
        row = Message(sender_id=me.user_id, receiver_id=other.user_id, type="text", body=data.body, priority="standard")
        db.add(row)
        db.commit()
        db.refresh(row)
    preview = row.body if len(row.body) <= PREVIEW else row.body[: PREVIEW - 1] + "…"
    ns.notify(
        db, other.user_id, "message", ns.STANDARD, (me.full_name or "").strip() or "New message", preview,
        dependent_id=dep_id, dedupe_key=f"message:{row.message_id}", extra={"message_id": str(row.message_id), "from_user_id": str(me.user_id)},
    )
    return _out(row, me)


def history(db: Session, me: User, with_user_id: uuid.UUID, *, limit: int, before: datetime | None) -> MessageList:
    other, _ = _pair(db, me, with_user_id)
    q = select(Message).where(
        or_(
            and_(Message.sender_id == me.user_id, Message.receiver_id == other.user_id),
            and_(Message.sender_id == other.user_id, Message.receiver_id == me.user_id),
        )
    )
    if before is not None:
        q = q.where(Message.sent_at < before)
    rows = list(db.scalars(q.order_by(Message.sent_at.desc(), Message.message_id.desc()).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    return MessageList(items=[_out(m, me) for m in rows], next_before=rows[-1].sent_at if more else None)


def conversations(db: Session, me: User) -> ConversationList:
    partner = case((Message.sender_id == me.user_id, Message.receiver_id), else_=Message.sender_id)
    rn = func.row_number().over(partition_by=partner, order_by=(Message.sent_at.desc(), Message.message_id.desc()))
    sub = (
        select(Message.message_id, partner.label("partner"), rn.label("rn"))
        .where(or_(Message.sender_id == me.user_id, Message.receiver_id == me.user_id))
        .subquery()
    )
    last = list(
        db.execute(
            select(Message, sub.c.partner).join(sub, sub.c.message_id == Message.message_id).where(sub.c.rn == 1)
            .order_by(Message.sent_at.desc())
        )
    )
    unread = dict(
        db.execute(
            select(Message.sender_id, func.count()).where(Message.receiver_id == me.user_id, Message.read_at.is_(None))
            .group_by(Message.sender_id)
        ).all()
    )
    items: list[ConversationOut] = []
    for m, pid in last:
        try:
            other, _ = _pair(db, me, pid)  # hide people I may no longer talk to
        except AppError:
            continue
        items.append(
            ConversationOut(user_id=pid, name=other.full_name, role=other.role, last_message=_out(m, me), unread_count=unread.get(pid, 0))
        )
    return ConversationList(items=items, total_unread=sum(i.unread_count for i in items))


def mark_read(db: Session, me: User, data: ReadIn) -> ReadOut:
    other, _ = _pair(db, me, data.with_user_id)
    res = db.execute(
        update(Message)
        .where(Message.sender_id == other.user_id, Message.receiver_id == me.user_id, Message.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
    return ReadOut(marked_read=res.rowcount)
