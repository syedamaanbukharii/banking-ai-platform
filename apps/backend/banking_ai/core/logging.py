"""Structured logging.

Uses structlog to emit JSON logs in production and human-friendly console logs
in dev. A redaction processor scrubs known-sensitive keys so secrets and PII do
not land in logs (required by the spec security rules).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

# Keys whose values must never be logged verbatim.
_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "groq_api_key",
    "client_secret",
    "ssn",
    "card_number",
    "account_number",
    "jwt",
}

_REDACTED = "***redacted***"


def _redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact sensitive values by key name (case-insensitive, substring match)."""
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if any(s in lowered for s in _SENSITIVE_KEYS):
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure stdlib + structlog. Idempotent; safe to call at startup."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_processor,
    ]

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """Bind request-scoped key/values (e.g. request_id, user_id) to all logs."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
