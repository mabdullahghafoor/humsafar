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


class FcmPushProvider:
    """Real Firebase Cloud Messaging sender. Needs PUSH_PROVIDER=fcm and FIREBASE_CREDENTIALS_JSON.

    'critical' messages use the high-priority Android channel (rings through quiet mode on the phone);
    'standard' ones use the normal channel. Dead tokens are only logged here; the row is already in the inbox.
    """

    def __init__(self) -> None:
        import json

        import firebase_admin
        from firebase_admin import credentials

        raw = get_settings().FIREBASE_CREDENTIALS_JSON
        if not raw:
            raise RuntimeError("PUSH_PROVIDER=fcm needs FIREBASE_CREDENTIALS_JSON (the service-account JSON).")
        try:
            self._app = firebase_admin.get_app("humsafar")
        except ValueError:
            self._app = firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)), name="humsafar")

    def send(self, message: PushMessage) -> None:
        from firebase_admin import messaging

        s = get_settings()
        critical = message.priority == "critical"
        channel = s.FCM_CRITICAL_CHANNEL_ID if critical else s.FCM_STANDARD_CHANNEL_ID
        data = {str(k): str(v) for k, v in message.data.items()}
        data["priority"] = message.priority
        for i in range(0, len(message.tokens), 500):  # FCM allows 500 tokens per call
            batch = message.tokens[i:i + 500]
            multicast = messaging.MulticastMessage(
                tokens=batch,
                notification=messaging.Notification(title=message.title, body=message.body),
                data=data,
                android=messaging.AndroidConfig(
                    priority="high" if critical else "normal",
                    notification=messaging.AndroidNotification(channel_id=channel),
                ),
            )
            result = messaging.send_each_for_multicast(multicast, app=self._app)
            log.info("FCM [%s] %s -> %d ok, %d failed", message.priority, message.title, result.success_count, result.failure_count)
            for tok, resp in zip(batch, result.responses):
                if not resp.success:
                    log.warning("FCM token ...%s failed: %s", tok[-6:], resp.exception)
            if result.success_count == 0:
                raise RuntimeError("FCM accepted none of the tokens")


_provider: PushProvider | None = None


def get_provider() -> PushProvider:
    global _provider
    if _provider is None:
        name = get_settings().PUSH_PROVIDER
        if name == "mock":
            _provider = MockPushProvider()
        elif name == "fcm":
            _provider = FcmPushProvider()
        else:
            raise RuntimeError(f"Unknown PUSH_PROVIDER '{name}'. Use 'mock' or 'fcm'.")
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
