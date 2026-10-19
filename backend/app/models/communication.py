"""
Communication module (SDS 8 / 9.2): messages, call_logs, notifications.

Traces to: FR-E1, FR-E2, FR-E4, FR-E5, FR-M1, FR-M2.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base
from app.models._common import fk_col, in_list, ts_col, uuid_pk

MESSAGE_TYPES = ("text", "priority_voice")
CALL_TYPES = ("voice", "video")
PRIORITY_TIERS = ("standard", "critical")  # FR-M1: at least two tiers


class Message(Base):
    __tablename__ = "messages"

    message_id = uuid_pk()
    sender_id = fk_col("users.user_id", index=True)
    receiver_id = fk_col("users.user_id")
    type = Column(String(20), nullable=False)
    # SDS 9.2 defines ONLY content_url (no text-body column). Nullable so text
    # messages are not blocked; see the open SDS gap raised with Task 1.1.
    content_url = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, server_default=text("'standard'"))
    sent_at = ts_col()
    # Task 4.2 (clarification 76): the SDS has no text column, so the text of a text message lives in `body`.
    body = Column(Text, nullable=True)
    # When the receiver opened the conversation. NULL = unread.
    read_at = Column(DateTime(timezone=True), nullable=True)
    # Chosen by the app for each message, so a retry on a bad network does not send it twice.
    client_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("type", MESSAGE_TYPES), name="type_valid"),
        CheckConstraint(in_list("priority", PRIORITY_TIERS), name="priority_valid"),
        CheckConstraint("type <> 'text' OR body IS NOT NULL", name="text_has_body"),
        CheckConstraint("body IS NULL OR char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        Index("ix_messages_receiver_sent", "receiver_id", "sent_at"),
        Index("uq_messages_sender_client", "sender_id", "client_id", unique=True, postgresql_where=text("client_id IS NOT NULL")),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    call_id = uuid_pk()
    caller_id = fk_col("users.user_id", index=True)
    callee_id = fk_col("users.user_id", index=True)
    type = Column(String(10), nullable=False)
    started_at = ts_col()
    duration_s = Column(Integer, nullable=True)  # NULL until the call ends

    __table_args__ = (
        CheckConstraint(in_list("type", CALL_TYPES), name="type_valid"),
        CheckConstraint("duration_s IS NULL OR duration_s >= 0", name="duration_nonneg"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = uuid_pk()
    user_id = fk_col("users.user_id")
    type = Column(String(40), nullable=False)
    priority = Column(String(20), nullable=False, server_default=text("'standard'"))
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    sent_at = ts_col()
    # FR-M2: NULL = delivered but not yet acknowledged ("no response" state).
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(in_list("priority", PRIORITY_TIERS), name="priority_valid"),
        Index("ix_notifications_user_sent", "user_id", "sent_at"),
        # Task 3.1 (clarification 28): one notification per person per event, even if two
        # processes dispatch at the same moment.
        Index(
            "uq_notifications_user_dedupe",
            "user_id",
            text("(payload ->> 'dedupe_key')"),
            unique=True,
            postgresql_where=text("(payload ->> 'dedupe_key') IS NOT NULL"),
        ),
    )


class PushToken(Base):
    """Task 3.1 (clarification 29): the phone's Firebase (FCM) token, so the server can push to it."""

    __tablename__ = "push_tokens"

    token_id = uuid_pk()
    user_id = fk_col("users.user_id", index=True)
    token = Column(Text, nullable=False, unique=True)
    platform = Column(String(20), nullable=False, server_default=text("'android'"))
    created_at = ts_col()
    last_seen_at = ts_col()
