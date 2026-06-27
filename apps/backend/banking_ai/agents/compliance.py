"""Compliance agent.

Answers a compliance/policy question by retrieving relevant policy chunks and
composing a grounded response with explicit citations (spec: compliance with
auditable, cited reasoning). The retrieval and citation assembly are
deterministic; if a model router is supplied, a natural-language synthesis is
produced on top of the cited evidence, otherwise a deterministic extractive
answer is returned. Either way the citations come only from retrieved chunks —
the agent never cites a source it did not retrieve.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.agents.retrieval import RetrievalAgent, RetrievalInput
from banking_ai.ai.router import ModelRouter
from banking_ai.ai.types import ChatMessage, CompletionRequest, Role
from banking_ai.ai.vector_store import Embedder, VectorStore
from banking_ai.prompts import get_prompt

PROMPT_VERSION = "compliance.v1"

_SYSTEM = get_prompt(PROMPT_VERSION)


class Citation(BaseModel):
    marker: int
    document_id: str
    chunk_id: str
    filename: str | None
    text: str


class ComplianceInput(BaseModel):
    question: str
    top_k: int = Field(default=4, ge=1, le=20)


class ComplianceOutput(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    grounded: bool
    model_used: str | None = None


class ComplianceAgent(BaseAgent[ComplianceInput, ComplianceOutput]):
    name = "compliance_agent"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        router: ModelRouter | None = None,
    ) -> None:
        super().__init__(router=router)
        self._retriever = RetrievalAgent(embedder=embedder, store=store)

    async def run(self, payload: ComplianceInput) -> ComplianceOutput:
        retrieval = await self._retriever.run(
            RetrievalInput(query=payload.question, top_k=payload.top_k)
        )
        citations = [
            Citation(
                marker=i + 1,
                document_id=str(hit.document_id),
                chunk_id=str(hit.chunk_id),
                filename=hit.filename,
                text=hit.text,
            )
            for i, hit in enumerate(retrieval.hits)
        ]

        if not citations:
            return ComplianceOutput(
                question=payload.question,
                answer="No relevant policy was found for this question.",
                citations=[],
                grounded=False,
            )

        # No router configured -> deterministic extractive answer.
        if self._router is None:
            joined = " ".join(f"[{c.marker}] {c.text}" for c in citations)
            answer = "Based on the retrieved policy excerpts: " + joined[:1500]
            return ComplianceOutput(
                question=payload.question,
                answer=answer,
                citations=citations,
                grounded=True,
            )

        # Router configured -> grounded synthesis over the cited evidence.
        evidence = "\n".join(f"[{c.marker}] {c.text}" for c in citations)
        request = CompletionRequest(
            messages=[
                ChatMessage(role=Role.SYSTEM, content=_SYSTEM),
                ChatMessage(
                    role=Role.USER,
                    content=f"Question: {payload.question}\n\nPolicy excerpts:\n{evidence}",
                ),
            ],
            max_tokens=512,
            temperature=0.0,
            prompt_version=self.prompt_version,
        )
        result = await self.router.complete(request)
        return ComplianceOutput(
            question=payload.question,
            answer=result.text.strip(),
            citations=citations,
            grounded=True,
            model_used=f"{result.provider}:{result.model}",
        )
