"""Agent executor.

Bridges a workflow's generic ``input_payload`` (a JSON dict) to the typed inputs
of individual agents and runs them, returning the uniform
:class:`~banking_ai.agents.base.AgentOutcome`. Keeping this mapping in one place
makes the in-process workflow runner simple and lets the same agents run
unchanged under a production orchestrator (Temporal) later.

Agents that need shared resources (model router, embedder, vector store) receive
them here; deterministic agents are constructed on demand.
"""

from __future__ import annotations

import uuid
from typing import Any

from banking_ai.agents.audit import AuditAgent, AuditInput
from banking_ai.agents.base import AgentOutcome
from banking_ai.agents.compliance import ComplianceAgent, ComplianceInput
from banking_ai.agents.document import DocumentAgent, DocumentAgentInput
from banking_ai.agents.fraud import FraudAgent, FraudInput, Transaction
from banking_ai.agents.kyc import KycAgent, KycInput
from banking_ai.agents.loan import LoanAgent, LoanInput
from banking_ai.agents.retrieval import RetrievalAgent, RetrievalInput
from banking_ai.agents.summarization import SummarizationAgent, SummarizationInput
from banking_ai.ai.router import ModelRouter
from banking_ai.ai.vector_store import Embedder, VectorStore
from banking_ai.core.errors import AgentError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)


class AgentExecutor:
    def __init__(
        self,
        *,
        router: ModelRouter | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._router = router
        self._embedder = embedder
        self._vector_store = vector_store

    async def run_step(self, agent_name: str, payload: dict[str, Any]) -> AgentOutcome:
        builder = getattr(self, f"_run_{agent_name}", None)
        if builder is None:
            raise AgentError(f"No executor mapping for agent '{agent_name}'.")
        return await builder(payload)

    # --- per-agent adapters ---

    async def _run_document_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = DocumentAgent()
        # A document_id is required by the schema; derive a stable one when the
        # workflow payload does not carry an explicit document reference.
        doc_id = payload.get("document_id") or payload.get("workflow_id") or str(uuid.uuid4())
        return await agent.execute(
            DocumentAgentInput(
                document_id=doc_id,
                kind=payload.get("kind", "generic"),
                text=payload.get("text", ""),
                extra_expected_fields=payload.get("extra_expected_fields", []),
            )
        )

    async def _run_kyc_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = KycAgent()
        return await agent.execute(
            KycInput(
                profile=payload.get("profile", {}),
                document_fields=payload.get("document_fields", {}),
            )
        )

    async def _run_fraud_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = FraudAgent()
        txn = payload.get("transaction", payload)
        return await agent.execute(
            FraudInput(
                transaction=Transaction(**txn),
                customer_avg_amount=payload.get("customer_avg_amount", 0.0),
            )
        )

    async def _run_loan_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = LoanAgent()
        return await agent.execute(LoanInput(**payload.get("loan", payload)))

    async def _run_summarization_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = SummarizationAgent(router=self._router)
        return await agent.execute(
            SummarizationInput(
                content=payload.get("text", payload.get("content", "")),
                max_sentences=payload.get("max_sentences", 5),
            )
        )

    async def _run_retrieval_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        self._require_retrieval()
        agent = RetrievalAgent(embedder=self._embedder, store=self._vector_store)  # type: ignore[arg-type]
        return await agent.execute(
            RetrievalInput(
                query=payload.get("query", payload.get("question", "")),
                top_k=payload.get("top_k", 5),
            )
        )

    async def _run_compliance_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        self._require_retrieval()
        agent = ComplianceAgent(
            embedder=self._embedder,  # type: ignore[arg-type]
            store=self._vector_store,  # type: ignore[arg-type]
            router=self._router,
        )
        return await agent.execute(
            ComplianceInput(
                question=payload.get("question", payload.get("query", "")),
                top_k=payload.get("top_k", 4),
            )
        )

    async def _run_audit_agent(self, payload: dict[str, Any]) -> AgentOutcome:
        agent = AuditAgent()
        return await agent.execute(
            AuditInput(
                workflow_id=str(payload.get("workflow_id", "")),
                evidence=payload.get("evidence", {}),
            )
        )

    def _require_retrieval(self) -> None:
        if self._embedder is None or self._vector_store is None:
            raise AgentError("Retrieval agents require an embedder and a vector store.")
