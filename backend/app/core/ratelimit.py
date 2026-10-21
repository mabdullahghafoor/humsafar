"""
Rate limiting for authentication and KYC endpoints (Task 6.5, SDS 17).

Two tools, both in memory (one server process; a shared store such as Redis is the upgrade when there are several):
  * `hit(scope, key, limit, window_s)`: counts every call (a plain per-IP limit).
  * failure counters: `blocked(scope, key, limit, window_s)` is checked BEFORE trying a password / code,
    `fail(scope, key)` records a wrong try, `clear(scope, key)` forgets them after a success.
Over the limit = `429 TOO_MANY_REQUESTS` with `Retry-After` and `details.retry_after_s`.
"""

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

_lock = threading.Lock()
_events: dict[tuple[str, str], deque] = defaultdict(deque)
_now = time.monotonic  # replaced in tests


def reset() -> None:
    with _lock:
        _events.clear()


def _trim(q: deque, window_s: float, now: float) -> None:
    while q and q[0] <= now - window_s:
        q.popleft()


def _too_many(retry_after: float) -> AppError:
    n = max(1, math.ceil(retry_after))
    return AppError(429, "TOO_MANY_REQUESTS", "Too many attempts. Please wait a moment and try again.", {"retry_after_s": n}, {"Retry-After": str(n)})


def hit(scope: str, key: str, limit: int, window_s: int) -> None:
    """Count one call; refuse it when `limit` calls already happened in the last `window_s` seconds."""
    if not get_settings().RATE_LIMIT_ENABLED:
        return
    now = _now()
    with _lock:
        q = _events[(scope, key)]
        _trim(q, window_s, now)
        if len(q) >= limit:
            raise _too_many(q[0] + window_s - now)
        q.append(now)


def blocked(scope: str, key: str, limit: int, window_s: int) -> None:
    """Raise 429 when `limit` failures were recorded in the last `window_s` seconds (does not count by itself)."""
    if not get_settings().RATE_LIMIT_ENABLED:
        return
    now = _now()
    with _lock:
        q = _events[(scope, key)]
        _trim(q, window_s, now)
        if len(q) >= limit:
            raise _too_many(q[0] + window_s - now)


def fail(scope: str, key: str) -> None:
    with _lock:
        _events[(scope, key)].append(_now())


def clear(scope: str, key: str) -> None:
    with _lock:
        _events.pop((scope, key), None)


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is read only when TRUST_PROXY_HEADERS is on (behind our own proxy), else it could be faked."""
    if get_settings().TRUST_PROXY_HEADERS:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def per_ip(scope: str, limit_name: str):
    """FastAPI dependency: `Depends(per_ip("login", "RATE_LOGIN_PER_MIN"))`."""
    def dep(request: Request) -> None:
        hit(scope, client_ip(request), getattr(get_settings(), limit_name), 60)
    return dep
