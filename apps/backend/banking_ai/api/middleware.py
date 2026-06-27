"""HTTP middleware: request id propagation and structured access logging."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from banking_ai.core.logging import bind_request_context, clear_request_context, get_logger

logger = get_logger(__name__)

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        bind_request_context(request_id=request_id, path=request.url.path)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("request.error", method=request.method, duration_ms=duration_ms)
            clear_request_context()
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[_REQUEST_ID_HEADER] = request_id
        logger.info(
            "request.completed",
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        clear_request_context()
        return response
