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
from app.core.config import get_settings
from app.services import notification_service as ns
from app.services import permission_service, storage_service

MODULE = "communication"
PREVIEW = 80

# Audio types the phone's recorder can produce, with the first bytes that prove it (we do not trust the file name).
def _sniff(data: bytes) -> str | None:
    if data[4:8] == b"ftyp":
        return ".m4a"  # MP4 / M4A / 3GP (AAC)
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if data[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return ".aac"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:4] == b"\x1aE\xdf\xa3":
        return ".webm"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if data[:6] == b"#!AMR\n" or data[:9] == b"#!AMR-WB\n":
        return ".amr"
    return None


def _pair(db: Session, me: User, other_id: uuid.UUID) -> tuple[User, uuid.UUID]:
    """Check that `me` and `other_id` may talk. Returns (other user, dependent_id) or raises 403."""
    other = db.get(User, other_id)
    if other is None or other.user_id == me.user_id or other.role == me.role:
        raise AppError(403, "NOT_LINKED_TO_DEPENDENT", "You can only contact a person you are linked to.")
    guardian, dep_id = (me, other.user_id) if me.role == "guardian" else (other, me.user_id)
    permission_service.check_module_access(db, guardian, dep_id, MODULE)
    return other, dep_id


def _out(m: Message, me: User, *, already: bool = False) -> MessageOut:
    return MessageOut(
        message_id=m.message_id, sender_id=m.sender_id, receiver_id=m.receiver_id, type=m.type, body=m.body,
        content_url=f"/messages/{m.message_id}/audio" if m.type == "priority_voice" else None, duration_s=m.duration_s, priority=m.priority, sent_at=m.sent_at, read_at=m.read_at,
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


# ------------------------------------------------------------ priority voice messages (Task 4.3, FR-E4)

def send_voice(db: Session, me: User, receiver_id: uuid.UUID, duration_s: int, data: bytes, client_id: uuid.UUID | None) -> MessageOut:
    if me.role != "guardian":
        raise AppError(403, "FORBIDDEN", "Only a Guardian can send a priority voice message.")
    other, dep_id = _pair(db, me, receiver_id)
    if not 1 <= duration_s <= get_settings().VOICE_MAX_S:
        raise AppError(422, "VALIDATION_ERROR", f"The voice message must be 1 to {get_settings().VOICE_MAX_S} seconds.")
    if not data:
        raise AppError(422, "VALIDATION_ERROR", "The audio file is empty.")
    if len(data) > get_settings().VOICE_MAX_BYTES:
        raise AppError(413, "AUDIO_TOO_LARGE", f"The audio file is too big (limit {get_settings().VOICE_MAX_BYTES // 1_000_000} MB).")
    ext = _sniff(data)
    if ext is None:
        raise AppError(415, "UNSUPPORTED_AUDIO", "This is not a supported audio file (m4a/aac, mp3, ogg, webm, wav, amr).")
    store = storage_service.get_storage()
    key = store.save(data, ext)
    stmt = (
        pg_insert(Message)
        .values(message_id=uuid.uuid4(), sender_id=me.user_id, receiver_id=other.user_id, type="priority_voice",
                content_url=key, duration_s=duration_s, priority="critical", client_id=client_id)
    )
    if client_id is not None:
        stmt = stmt.on_conflict_do_nothing(index_elements=["sender_id", "client_id"], index_where=text("client_id IS NOT NULL"))
    new_id = db.execute(stmt.returning(Message.message_id)).scalar()
    db.commit()
    if new_id is None:  # lost a race with an identical retry: drop our copy of the file, answer with the first message
        store.delete(key)
        old = db.scalar(select(Message).where(Message.sender_id == me.user_id, Message.client_id == client_id))
        return _repeat(old, me, other.user_id, "priority_voice", duration_s)
    row = db.get(Message, new_id)
    ns.notify(
        db, other.user_id, "voice_message", ns.CRITICAL, f"Voice message from {(me.full_name or '').strip() or 'your Guardian'}",
        f"{duration_s} second voice message", dependent_id=dep_id, dedupe_key=f"message:{row.message_id}",
        extra={"message_id": str(row.message_id), "from_user_id": str(me.user_id), "duration_s": duration_s},
    )
    return _out(row, me)


def _repeat(old: Message, me: User, receiver_id: uuid.UUID, type_: str, duration_s: int) -> MessageOut:
    if old.receiver_id != receiver_id or old.type != type_ or old.duration_s != duration_s:
        raise AppError(409, "CLIENT_ID_REUSED", "This client_id was already used for a different message.")
    return _out(old, me, already=True)


def audio_file(db: Session, me: User, message_id: uuid.UUID):
    """The saved audio of a voice message, for its sender or receiver (and only while they may still talk)."""
    m = db.get(Message, message_id)
    if m is None or m.type != "priority_voice" or me.user_id not in (m.sender_id, m.receiver_id):
        raise AppError(404, "MESSAGE_NOT_FOUND", "Voice message not found.")
    _pair(db, me, m.receiver_id if m.sender_id == me.user_id else m.sender_id)
    path = storage_service.get_storage().path(m.content_url)
    if path is None:
        raise AppError(404, "AUDIO_NOT_FOUND", "The audio file is no longer available.")
    return path
