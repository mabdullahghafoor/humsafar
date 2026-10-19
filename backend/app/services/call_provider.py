"""
Call provider boundary (Task 4.4, FR-E2). Decision 4.1: a hosted SDK (ZegoCloud) does the audio / video; our server only
decides WHO may join WHICH room and hands each person a short-lived join token. The Flutter app gives that token to the
SDK. Same pattern as push / SMS: one Protocol, a mock now, the real class later.

The real ZegoCloud class (its "token04") is added when Talha's App ID and Server Secret exist, so it can be checked against
the real service instead of guessed. Keys will live only in the backend `.env`, never in the app.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger("humsafar.call")


class CallProvider(Protocol):
    name: str

    def join_info(self, room_id: str, user_id: str, call_type: str) -> dict: ...


class MockCallProvider:
    """No real media. Gives a stable fake token so the app flow and tests can be built."""

    name = "mock"

    def __init__(self) -> None:
        self.issued: list[tuple[str, str]] = []  # (room_id, user_id), newest last
        self.fail = False

    def join_info(self, room_id: str, user_id: str, call_type: str) -> dict:
        if self.fail:
            raise RuntimeError("mock call provider is down")
        self.issued.append((room_id, user_id))
        ttl = get_settings().CALL_TOKEN_TTL_S
        return {
            "provider": "mock",
            "app_id": "mock-app",
            "room_id": room_id,
            "user_id": user_id,
            "token": "mock-" + hashlib.sha256(f"{room_id}:{user_id}".encode()).hexdigest()[:32],
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
        }


_provider: CallProvider | None = None


def get_provider() -> CallProvider:
    global _provider
    if _provider is None:
        name = get_settings().CALL_PROVIDER
        if name != "mock":
            raise RuntimeError(f"Unknown CALL_PROVIDER '{name}'. Only 'mock' exists until the ZegoCloud keys are available.")
        _provider = MockCallProvider()
    return _provider


def join_info(room_id: str, user_id: str, call_type: str) -> dict | None:
    """Never raises. None = the provider could not give a token (the app asks again with GET /calls/{id})."""
    try:
        return get_provider().join_info(room_id, user_id, call_type)
    except Exception:  # noqa: BLE001
        log.exception("call provider failed")
        return None
