"""Error envelope: every error body is the `Error` schema {code, message, details?}."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

# Explicit status -> ErrorCode (openapi Error.code known values). INTERNAL_ERROR is not in that list
# (no 5xx code is documented); logged in progress.md as a contract question.
_STATUS_CODES = {
    401: "TOKEN_INVALID",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "NOT_IMPLEMENTED",
    429: "RATE_LIMITED",
    501: "NOT_IMPLEMENTED",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None):
        self.headers = headers
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else {}
        headers.update(exc.headers or {})
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status,
                            headers=headers or None)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path", "header")]
            fields.append({"field": ".".join(loc), "message": str(err["msg"])})
        return JSONResponse(
            _body("VALIDATION_ERROR", "Request validation failed", {"fields": fields}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code)
        if code is None:
            code = "VALIDATION_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR"
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code, headers=headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(_body("INTERNAL_ERROR", "Internal server error"), status_code=500)
