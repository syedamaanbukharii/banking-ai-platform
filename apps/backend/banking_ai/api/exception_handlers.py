"""Exception handlers rendering the canonical error envelope.

Every error path returns ``{"error": {"code", "message", "details"}}`` so clients
branch on a stable ``code`` rather than parsing prose.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from banking_ai.core.errors import AppError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": {"errors": _safe_errors(exc)},
            }
        },
    )


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("request.unhandled_exception", error=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {},
            }
        },
    )


def _safe_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for err in exc.errors():
        out.append(
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return out


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
