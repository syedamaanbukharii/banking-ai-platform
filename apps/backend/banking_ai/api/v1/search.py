"""Semantic search endpoint (RAG retrieval over indexed document chunks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from banking_ai.agents.retrieval import RetrievalAgent, RetrievalInput
from banking_ai.api.deps import StateDep, require_permissions
from banking_ai.core.errors import AgentError
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal
from banking_ai.schemas.audit import SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    state: StateDep,
    q: str = Query(..., min_length=1, max_length=1000, description="Search query"),
    top_k: int = Query(default=5, ge=1, le=50),
    principal: Principal = Depends(require_permissions(Permission.SEARCH_READ.value)),
) -> SearchResponse:
    agent = RetrievalAgent(embedder=state.embedder, store=state.vector_store)
    outcome = await agent.execute(RetrievalInput(query=q, top_k=top_k))
    if outcome.output is None:
        raise AgentError(outcome.error or "Search failed.")
    return SearchResponse(query=q, hits=outcome.output.hits)
