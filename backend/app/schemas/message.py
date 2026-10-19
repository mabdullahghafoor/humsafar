"""Schemas for text messaging (Task 4.2, FR-E1)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MessageIn(BaseModel):
    receiver_id: UUID = Field(description="The other person: a Guardian writes to a linked Dependent, a Dependent to a linked Guardian.")
    body: str = Field(min_length=1, max_length=2000, description="The text. Spaces at both ends are removed.")
    client_id: UUID | None = Field(
        default=None,
        description="Optional. A new random id the app makes for each message. If the app sends the same message again "
        "(bad network), the server answers with the first one instead of sending twice.",
    )

    @field_validator("body")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("The message is empty.")
        return v


class MessageOut(BaseModel):
    message_id: UUID
    sender_id: UUID
    receiver_id: UUID
    type: Literal["text", "priority_voice"]
    body: str | None = Field(default=None, description="The text (text messages).")
    content_url: str | None = Field(default=None, description="The audio (priority voice messages, Task 4.3).")
    priority: Literal["standard", "critical"]
    sent_at: datetime
    read_at: datetime | None = Field(default=None, description="When the receiver opened it. Null = not read yet.")
    from_me: bool = Field(description="True if the person asking sent it.")
    already_sent: bool = Field(default=False, description="Only on POST: true if this `client_id` was sent before (nothing new was sent).")


class MessageList(BaseModel):
    items: list[MessageOut] = Field(description="Newest first.")
    next_before: datetime | None = Field(default=None, description="Pass as `before` to get the next (older) page. Null = no more.")


class ConversationOut(BaseModel):
    user_id: UUID = Field(description="The other person.")
    name: str
    role: Literal["guardian", "dependent"]
    last_message: MessageOut
    unread_count: int = Field(description="Messages from them that you have not opened yet.")


class ConversationList(BaseModel):
    items: list[ConversationOut] = Field(description="Most recent conversation first.")
    total_unread: int


class ReadIn(BaseModel):
    with_user_id: UUID = Field(description="Mark every message from this person as read.")


class ReadOut(BaseModel):
    marked_read: int
