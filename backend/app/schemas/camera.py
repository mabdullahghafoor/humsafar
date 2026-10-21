"""Schemas for the camera (Task 6.3, FR-K1)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CameraPairIn(BaseModel):
    name: str | None = Field(default=None, max_length=60, description="Optional label, for example 'Living room'.")

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if isinstance(v, str) and "\x00" in v:
            raise ValueError("This text contains a character that is not allowed.")
        v = v.strip() if isinstance(v, str) else v
        return v or None


class CameraStatus(BaseModel):
    paired: bool
    camera_id: UUID | None = None
    name: str | None = None
    paired_at: datetime | None = None
    online: bool = Field(description="true when the camera phone sent a heartbeat in the last 30 seconds.")
    last_seen_at: datetime | None = None
    viewers_now: int = Field(description="Guardians watching right now.")
    max_viewers: int


class RoomJoin(BaseModel):
    provider: str
    app_id: str
    room_id: str
    stream_id: str = Field(description="The camera phone publishes this stream id; the viewer plays it.")
    user_id: str = Field(description="Log in to the room with exactly this user id.")
    token: str
    expires_at: datetime


class StreamOut(BaseModel):
    session_id: UUID
    dependent_id: UUID
    camera_name: str | None = None
    started_at: datetime
    expires_at: datetime = Field(description="The session ends then unless you call GET .../camera/stream again before it.")
    renew_every_s: int = Field(description="Call GET .../camera/stream again this often while watching.")
    join: RoomJoin
    renewed: bool = Field(description="true when you already had an open session and it was extended.")


class HeartbeatOut(BaseModel):
    should_publish: bool = Field(description="true while at least one Guardian is watching: start (or keep) publishing. false: stop publishing and save battery.")
    viewers_now: int
    next_poll_s: int = Field(description="Send the next heartbeat after this many seconds.")
    join: RoomJoin | None = Field(default=None, description="Present when should_publish is true. null while should_publish = true means the provider is unavailable: ask again at the next poll.")


class Viewer(BaseModel):
    user_id: UUID
    full_name: str
    role: Literal["primary", "secondary"]
    since: datetime


class ViewingOut(BaseModel):
    being_viewed: bool
    viewers: list[Viewer]
