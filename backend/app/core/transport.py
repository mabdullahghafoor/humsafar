"""
Transport security (Task 6.5, FR-N1 / SDS 17: TLS 1.2+ for all client-server traffic).

The server itself speaks plain http; TLS ends at the host's proxy (Render, nginx, a cloud load balancer) in front of it. This module
  * refuses plain-http requests when ENFORCE_HTTPS is on (`400 HTTPS_REQUIRED`; `/health` stays open for the host's health check),
  * adds HSTS on https responses and the standard hardening headers on every response,
  * checks the production settings at start-up (`production_problems`) so a deployment cannot go live with a default secret, no file
    encryption key, debug on, or a database connection without TLS.
Behind a proxy set TRUST_PROXY_HEADERS=true so the original scheme (X-Forwarded-Proto) is believed; otherwise that header is ignored.
"""

import logging
from urllib.parse import parse_qs, urlparse

from starlette.responses import JSONResponse

from app.core.config import DEFAULT_JWT_SECRET, Settings, get_settings

log = logging.getLogger("humsafar.security")
OPEN_OVER_HTTP = {"/health"}

HARDENING_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
]


def request_scheme(scope) -> str:
    if get_settings().TRUST_PROXY_HEADERS:
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-proto":
                return v.decode("latin-1").split(",")[0].strip().lower()
    return scope.get("scheme", "http")


class TransportSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        s = get_settings()
        secure = request_scheme(scope) in ("https", "wss")
        if s.ENFORCE_HTTPS and not secure and scope.get("path") not in OPEN_OVER_HTTP:
            resp = JSONResponse({"error": {"code": "HTTPS_REQUIRED", "message": "This service only accepts https connections.", "details": {}}}, status_code=400)
            return await resp(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                have = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in HARDENING_HEADERS if k not in have]
                if secure and b"strict-transport-security" not in have:
                    headers.append((b"strict-transport-security", f"max-age={s.HSTS_MAX_AGE_S}; includeSubDomains".encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _local_db(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "")


def production_problems(s: Settings) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors stop a production start; warnings are logged."""
    errors, warnings = [], []
    if s.JWT_SECRET_KEY == DEFAULT_JWT_SECRET or len(s.JWT_SECRET_KEY) < 32:
        errors.append("JWT_SECRET_KEY is the default or shorter than 32 characters.")
    if not s.RECORDS_ENCRYPTION_KEY or len(s.RECORDS_ENCRYPTION_KEY) < 32:
        errors.append("RECORDS_ENCRYPTION_KEY is empty or shorter than 32 characters (record files and clips would be encrypted with a key derived from the JWT secret).")
    if s.DEBUG:
        errors.append("DEBUG is on.")
    if not s.ENFORCE_HTTPS:
        errors.append("ENFORCE_HTTPS is off (plain http would be accepted).")
    if not s.RATE_LIMIT_ENABLED:
        errors.append("RATE_LIMIT_ENABLED is off (no brute-force protection on login and OTP).")
    if not _local_db(s.DATABASE_URL):
        mode = (parse_qs(urlparse(s.DATABASE_URL).query).get("sslmode") or [""])[0]
        if mode not in ("require", "verify-ca", "verify-full"):
            errors.append("DATABASE_URL points to a remote database without sslmode=require (or verify-ca / verify-full).")
    for name in ("KYC_PROVIDER", "PUSH_PROVIDER", "SMS_PROVIDER", "CALL_PROVIDER"):
        if getattr(s, name) == "mock":
            warnings.append(f"{name} is still the mock provider.")
    if s.WEARABLE_MOCK_ENABLED:
        warnings.append("WEARABLE_MOCK_ENABLED is on (demo band data endpoint is open).")
    return errors, warnings


def enforce_startup(s: Settings) -> None:
    """Called when the app starts. ENVIRONMENT=production refuses to start with errors; other environments only log them."""
    errors, warnings = production_problems(s)
    if s.ENVIRONMENT == "production":
        for w in warnings:
            log.warning("production check: %s", w)
        if errors:
            raise RuntimeError("Refusing to start in production: " + " ".join(errors))
