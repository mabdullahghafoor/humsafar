"""Schemas for voice and video calls (Task 4.4, FR-E2)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CallIn(BaseModel):
    callee_id: UUID = Field(description="The other person: a Guardian calls a linked Dependent, a Dependent calls a linked Guardian.")
    type: Literal["voice", "video"] = "voice"


class JoinInfo(BaseModel):
    provider: str = Field(description="'zego' (real) or 'mock'.")
    app_id: str
    room_id: str
    user_id: str = Field(description="The id to use inside the call provider's SDK.")
    token: str = Field(description="Short-lived. Give it to the call SDK. Never log it.")
    expires_at: datetime


class CallOut(BaseModel):
    call_id: UUID
    caller_id: UUID
    callee_id: UUID
    type: Literal["voice", "video"]
    status: Literal["ringing", "accepted", "ended", "declined", "missed", "cancelled"]
    started_at: datetime
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_s: int | None = Field(default=None, description="Seconds from answer to end (only for answered calls).")
    from_me: bool = Field(description="True if the person asking made the call.")
    other_name: str = Field(description="The other person's name.")
    already_active: bool = Field(default=False, description="Only on POST /calls: true if this same call was already ringing or running (nothing new was sent).")
    ring_expires_at: datetime | None = Field(default=None, description="While ringing: when it becomes 'missed' if nobody answers.")
    join: JoinInfo | None = Field(
        default=None,
        description="To join the call. The caller gets it at once; the callee gets it after accepting. Null otherwise. If null while it should not be, call GET /calls/{id}.",
    )


class CallList(BaseModel):
    items: list[CallOut] = Field(description="Newest first.")
    next_before: datetime | None = None
