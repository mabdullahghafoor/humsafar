"""
Push delivery boundary (Task 3.1, SDS 3.3: push goes through the Android notification system / Firebase).

Everything else calls `deliver(...)`. A real Firebase (FCM) provider will be one new class here, written
when Talha's Firebase project exists (Task 3.14). Until then the mock records what WOULD have been sent,
so tests and demos can see it. A push failure must never lose a notification: the notification row is
already saved and shows up in the inbox (GET /notifications).
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger("humsafar.push")


@dataclass(frozen=True)
class PushMessage:
    tokens: list[str]
    title: str
    body: str
    priority: str  # 'critical' -> high-priority Android channel, 'standard' -> normal
    data: dict = field(default_factory=dict)


class PushProvider(Protocol):
    def send(self, message: PushMessage) -> None: ...


class MockPushProvider:
    """Remembers every message in `sent` (newest last). Set `fail = True` to simulate Firebase being down."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []
        self.fail = False

    def send(self, message: PushMessage) -> None:
        if self.fail:
            raise RuntimeError("mock push provider is down")
        self.sent.append(message)
        log.info("MOCK PUSH [%s] %s -> %d device(s)", message.priority, message.title, len(message.tokens))


_provider: PushProvider | None = None


def get_provider() -> PushProvider:
    global _provider
    if _provider is None:
        name = get_settings().PUSH_PROVIDER
        if name != "mock":
            raise RuntimeError(f"Unknown PUSH_PROVIDER '{name}'. Only 'mock' exists until Firebase is set up.")
        _provider = MockPushProvider()
    return _provider


def deliver(message: PushMessage) -> bool:
    """Send; never raises. Returns True if the provider accepted it."""
    if not message.tokens:
        return False
    try:
        get_provider().send(message)
        return True
    except Exception:  # noqa: BLE001  (push is best effort; the inbox row is the record)
        log.exception("push delivery failed")
        return False
