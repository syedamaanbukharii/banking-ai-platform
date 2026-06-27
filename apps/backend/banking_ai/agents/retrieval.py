"""Retrieval agent.

Wraps an :class:`Embedder` and a :class:`VectorStore` to turn a natural-language
query into ranked document chunks. Deterministic given a deterministic embedder
and store, so it is fully testable offline.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.ai.vector_store import Embedder, VectorStore
from banking_ai.schemas.audit import SearchHit


class RetrievalInput(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class RetrievalOutput(BaseModel):
    query: str
    hits: list[SearchHit]


class RetrievalAgent(BaseAgent[RetrievalInput, RetrievalOutput]):
    name = "retrieval_agent"

    def __init__(self, *, embedder: Embedder, store: VectorStore) -> None:
        super().__init__(router=None)
        self._embedder = embedder
        self._store = store

    async def run(self, payload: RetrievalInput) -> RetrievalOutput:
        embedding = self._embedder.embed(payload.query)
        scored = await self._store.query(embedding, top_k=payload.top_k)
        hits = [
            SearchHit(
                document_id=uuid.UUID(s.record.document_id),
                chunk_id=uuid.UUID(s.record.chunk_id),
                score=round(s.score, 6),
                text=s.record.text,
                filename=s.record.filename,
            )
            for s in scored
        ]
        return RetrievalOutput(query=payload.query, hits=hits)
