"""
Standard error envelope (SDS 11.2) used by EVERY endpoint:

    { "error": { "code": "string", "message": "string", "details": {} } }

`code` is a stable machine-readable string the Flutter app can switch on;
`message` is human-readable; `details` carries extra structured info.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Raise anywhere in the backend to return a clean SDS-format error."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "TOO_MANY_REQUESTS",
}


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
        headers=exc.headers,
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        fields.append(
            {
                "field": ".".join(loc),
                "message": str(err.get("msg", "Invalid value")).removeprefix("Value error, "),
            }
        )
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", "One or more fields are invalid.", {"fields": fields}),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals to the client.
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "Something went wrong on our side."),
    )


async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    # Found in Task 5.1: text with a NUL character (0x00) makes the database driver raise ValueError for ANY endpoint
    # that saves text. It is the caller's bad input, so answer 422 instead of 500. Any other ValueError is a real bug: let it through.
    if "NUL" in str(exc) and "0x00" in str(exc):
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "A text field contains a character that is not allowed.", {"fields": []}),
        )
    raise exc


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(ValueError, _value_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
