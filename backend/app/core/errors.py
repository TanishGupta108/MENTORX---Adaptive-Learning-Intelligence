"""One error shape for every failure: {"error": {"code", "message", "request_id"}} (NFR-REL-03)."""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.request")
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class AppError(Exception):
    """A domain error with a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def _body(code: str, message: str, **extra) -> dict:
    return {
        "error": {"code": code, "message": message, "request_id": request_id_var.get(), **extra}
    }


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        # A client-supplied ID is reused only if it's short and plain (it ends up in the logs).
        given = request.headers.get("x-request-id", "")
        rid = given if _SAFE_REQUEST_ID.fullmatch(given) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        logger.info(
            "%s %s -> %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            extra={"request_id": rid},
        )
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message), exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            _body("validation_error", "Some fields are invalid.", fields=fields),
            422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthenticated"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(_body(code, str(exc.detail)), exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error rid=%s", request_id_var.get())
        return JSONResponse(
            _body("internal_error", "Something went wrong. Please try again."),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
