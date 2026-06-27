"""Audit service.

Centralises append-only writes to ``audit_logs``. The service never updates or
deletes audit rows. Context is redacted before persistence so secrets never land
in the audit trail (defence in depth alongside the logging redactor).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from banking_ai.core.logging import get_logger
from banking_ai.db.models.observability import AuditLog

logger = get_logger(__name__)

_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "ssn",
    "card_number",
}


def _redact(context: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in context.items():
        if key.lower() in _SENSITIVE_KEYS:
            redacted[key] = "***redacted***"
        else:
            redacted[key] = value
    return redacted


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        outcome: str = "success",
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        resource_id: str | None = None,
        request_id: str | None = None,
        context: dict[str, object] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            outcome=outcome,
            actor_id=actor_id,
            actor_email=actor_email,
            resource_id=resource_id,
            request_id=request_id,
            context=_redact(context or {}),
        )
        self._session.add(entry)
        await self._session.flush()
        logger.info(
            "audit.recorded",
            action=action,
            resource_type=resource_type,
            outcome=outcome,
            resource_id=resource_id,
        )
        return entry
