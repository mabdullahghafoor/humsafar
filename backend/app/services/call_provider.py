"""
Call provider boundary (Task 4.4, FR-E2). Decision 4.1: a hosted SDK (ZegoCloud) does the audio / video; our server only
decides WHO may join WHICH room and hands each person a short-lived join token. The Flutter app gives that token to the
SDK. Same pattern as push / SMS: one Protocol, a mock now, the real class later.

`ZegoProvider` makes the real ZegoCloud "token04" (AES-256-GCM, same format as ZegoCloud's own open-source generator
https://github.com/zegoim/zego_server_assistant). The App ID and Server Secret live only in the backend `.env`, never in the app.
"""

import base64
import hashlib
import json
import logging
import random
import string
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

log = logging.getLogger("humsafar.call")


class CallProvider(Protocol):
    name: str

    def join_info(self, room_id: str, user_id: str, call_type: str) -> dict: ...

    def room_token(self, room_id: str, user_id: str, *, publish: bool, ttl_s: int) -> dict: ...  # Task 6.3 (camera room)


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


    def room_token(self, room_id: str, user_id: str, *, publish: bool, ttl_s: int) -> dict:
        if self.fail:
            raise RuntimeError("mock call provider is down")
        self.issued.append((room_id, user_id))
        return {
            "provider": "mock", "app_id": "mock-app", "room_id": room_id, "user_id": user_id,
            "token": ("mock-pub-" if publish else "mock-view-") + hashlib.sha256(f"{room_id}:{user_id}:{publish}".encode()).hexdigest()[:32],
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_s),
        }


def make_token04(app_id: int, user_id: str, secret: str, ttl_s: int, payload: str, *, now: int | None = None) -> str:
    """ZegoCloud token04: "04" + base64( expire(8, big-endian) | len(nonce)(2) | nonce | len(data)(2) | AES-GCM(json)+tag | 1 )."""
    if not isinstance(app_id, int) or app_id <= 0:
        raise ValueError("ZEGO_APP_ID must be a positive number")
    if not user_id:
        raise ValueError("user_id is empty")
    if len(secret) != 32:
        raise ValueError("ZEGO_SERVER_SECRET must be 32 characters")
    created = int(now if now is not None else time.time())
    expire = created + ttl_s
    info = {"app_id": app_id, "user_id": user_id, "nonce": random.SystemRandom().randint(1, 90_000_000),
            "ctime": created, "expire": expire, "payload": payload}
    plain = json.dumps(info, separators=(",", ":"), ensure_ascii=False).encode()
    nonce = "".join(random.SystemRandom().choice(string.digits + string.ascii_lowercase) for _ in range(12))
    sealed = AESGCM(secret.encode()).encrypt(nonce.encode(), plain, None)  # ciphertext + 16-byte tag
    raw = struct.pack("!q", expire) + struct.pack("!h", len(nonce)) + nonce.encode() + struct.pack("!h", len(sealed)) + sealed + b"\x01"
    return "04" + base64.b64encode(raw).decode()


class ZegoProvider:
    """Real ZegoCloud join tokens. One token per person per call; it only allows login to THIS room and publishing a stream."""

    name = "zego"

    def __init__(self, app_id: int, secret: str) -> None:
        make_token04(app_id, "check", secret, 60, "")  # fail at start-up if the keys are wrong, not in the middle of a call
        self.app_id, self.secret = app_id, secret

    def join_info(self, room_id: str, user_id: str, call_type: str) -> dict:
        ttl = get_settings().CALL_TOKEN_TTL_S
        payload = json.dumps({"room_id": room_id, "privilege": {1: 1, 2: 1}, "stream_id_list": None})  # 1 = login room, 2 = publish stream
        return {
            "provider": "zego",
            "app_id": str(self.app_id),
            "room_id": room_id,
            "user_id": user_id,
            "token": make_token04(self.app_id, user_id, self.secret, ttl, payload),
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
        }


    def room_token(self, room_id: str, user_id: str, *, publish: bool, ttl_s: int) -> dict:
        """Camera room token: a viewer may log in and watch (privilege 1) but NOT publish; the camera phone may publish (privilege 2)."""
        payload = json.dumps({"room_id": room_id, "privilege": {1: 1, 2: 1 if publish else 0}, "stream_id_list": None})
        return {
            "provider": "zego", "app_id": str(self.app_id), "room_id": room_id, "user_id": user_id,
            "token": make_token04(self.app_id, user_id, self.secret, ttl_s, payload),
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_s),
        }


_provider: CallProvider | None = None


def get_provider() -> CallProvider:
    global _provider
    if _provider is None:
        name = get_settings().CALL_PROVIDER
        if name == "mock":
            _provider = MockCallProvider()
        elif name == "zego":
            cfg = get_settings()
            _provider = ZegoProvider(cfg.ZEGO_APP_ID, cfg.ZEGO_SERVER_SECRET)
        else:
            raise RuntimeError(f"Unknown CALL_PROVIDER '{name}'. Use 'mock' or 'zego'.")
    return _provider


def join_info(room_id: str, user_id: str, call_type: str) -> dict | None:
    """Never raises. None = the provider could not give a token (the app asks again with GET /calls/{id})."""
    try:
        return get_provider().join_info(room_id, user_id, call_type)
    except Exception:  # noqa: BLE001
        log.exception("call provider failed")
        return None


def room_token(room_id: str, user_id: str, *, publish: bool, ttl_s: int) -> dict | None:
    """Never raises. None = the provider could not give a token."""
    try:
        return get_provider().room_token(room_id, user_id, publish=publish, ttl_s=ttl_s)
    except Exception:  # noqa: BLE001
        log.exception("call provider failed (camera room token)")
        return None
