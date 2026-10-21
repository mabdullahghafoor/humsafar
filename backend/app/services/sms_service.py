"""
SMS gateway boundary (Task 3.8, SRS 3.3 "SMS/voice gateway interface"; FR-R1).

Everything calls `send(to, body)`. A real gateway (a Pakistani SMS provider, Twilio, ...) is one new class here.
Until then the mock remembers what WOULD have been sent, so tests and demos can see it. `send` never raises: it returns
True when the gateway accepted the message. (Same idea as push_service.)
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger("humsafar.sms")


@dataclass(frozen=True)
class SmsMessage:
    to: str  # E.164, e.g. +923001234567
    body: str


class SmsProvider(Protocol):
    def send(self, message: SmsMessage) -> None: ...


class MockSmsProvider:
    """Remembers every message in `sent` (newest last). Set `fail = True` to simulate the gateway being down."""

    def __init__(self) -> None:
        self.sent: list[SmsMessage] = []
        self.fail = False

    def send(self, message: SmsMessage) -> None:
        if self.fail:
            raise RuntimeError("mock SMS gateway is down")
        self.sent.append(message)
        log.info("MOCK SMS -> %s: %s", message.to, message.body)


_provider: SmsProvider | None = None


def get_provider() -> SmsProvider:
    global _provider
    if _provider is None:
        name = get_settings().SMS_PROVIDER
        if name != "mock":
            raise RuntimeError(f"Unknown SMS_PROVIDER '{name}'. Only 'mock' exists until a real gateway is chosen.")
        _provider = MockSmsProvider()
    return _provider


def send(to: str, body: str) -> bool:
    try:
        get_provider().send(SmsMessage(to=to, body=body))
        return True
    except Exception:  # noqa: BLE001  (the caller records the failure and retries)
        log.exception("SMS delivery failed")
        return False
