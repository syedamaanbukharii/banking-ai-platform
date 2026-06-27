"""Pydantic request/response schemas (the versioned API contract).

Schemas are intentionally separate from ORM models: the database layer can
evolve without changing the public contract, and vice versa.
"""

from __future__ import annotations

from banking_ai.schemas.audit import (
    ApprovalDecisionRequest,
    AuditLogOut,
    SearchHit,
    SearchResponse,
)
from banking_ai.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    TokenPair,
)
from banking_ai.schemas.common import (
    ApiModel,
    ErrorDetail,
    ErrorResponse,
    Page,
    PageMeta,
    PaginationParams,
)
from banking_ai.schemas.document import (
    DocumentChunkOut,
    DocumentOut,
    DocumentReview,
    ExtractedField,
)
from banking_ai.schemas.workflow import (
    AgentRunOut,
    ApprovalOut,
    TaskOut,
    WorkflowDetail,
    WorkflowOut,
    WorkflowStartRequest,
)

__all__ = [
    "AgentRunOut",
    "ApiModel",
    "ApprovalDecisionRequest",
    "ApprovalOut",
    "AuditLogOut",
    "CurrentUser",
    "DocumentChunkOut",
    "DocumentOut",
    "DocumentReview",
    "ErrorDetail",
    "ErrorResponse",
    "ExtractedField",
    "LoginRequest",
    "Page",
    "PageMeta",
    "PaginationParams",
    "RefreshRequest",
    "SearchHit",
    "SearchResponse",
    "TaskOut",
    "TokenPair",
    "WorkflowDetail",
    "WorkflowOut",
    "WorkflowStartRequest",
]
