"""Approval (HITL), search, and audit schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from banking_ai.schemas.common import ApiModel


class ApprovalDecisionRequest(ApiModel):
    """Body for approve / reject / escalate actions."""

    reason: str | None = Field(default=None, max_length=2000)


class SearchHit(ApiModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    score: float
    text: str
    filename: str | None = None


class SearchResponse(ApiModel):
    query: str
    hits: list[SearchHit]


class AuditLogOut(ApiModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    context: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
