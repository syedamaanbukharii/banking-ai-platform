"""Document-intelligence schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from banking_ai.db.models.enums import DocumentStatus
from banking_ai.schemas.common import ApiModel


class DocumentOut(ApiModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    doc_metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class DocumentChunkOut(ApiModel):
    id: uuid.UUID
    chunk_index: int
    text: str


class ExtractedField(ApiModel):
    name: str
    value: str | None
    present: bool


class DocumentReview(ApiModel):
    """Deterministic review output from the document agent."""

    document_id: uuid.UUID
    summary: str
    extracted_fields: list[ExtractedField]
    missing_fields: list[str]
    review_notes: list[str]
    requires_human_review: bool
