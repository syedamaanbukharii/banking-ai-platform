"""Specialised agents.

Each agent has one responsibility, typed I/O, structured logging, and is
independently testable. Agents whose output is model-generated call the model
router; their deterministic logic does not require any model.
"""

from __future__ import annotations

from banking_ai.agents.audit import AuditAgent, AuditBundle, AuditInput
from banking_ai.agents.base import AgentOutcome, BaseAgent
from banking_ai.agents.compliance import (
    ComplianceAgent,
    ComplianceInput,
    ComplianceOutput,
)
from banking_ai.agents.document import DocumentAgent, DocumentAgentInput
from banking_ai.agents.fraud import FraudAgent, FraudInput, FraudResult, Transaction
from banking_ai.agents.kyc import KycAgent, KycInput, KycResult
from banking_ai.agents.loan import LoanAgent, LoanInput, LoanResult
from banking_ai.agents.notification import (
    NotificationAgent,
    NotificationInput,
    NotificationOutput,
)
from banking_ai.agents.orchestrator import (
    OrchestratorAgent,
    OrchestratorInput,
    WorkflowPlan,
)
from banking_ai.agents.retrieval import RetrievalAgent, RetrievalInput, RetrievalOutput
from banking_ai.agents.summarization import (
    SummarizationAgent,
    SummarizationInput,
    SummarizationOutput,
)

__all__ = [
    "AgentOutcome",
    "AuditAgent",
    "AuditBundle",
    "AuditInput",
    "BaseAgent",
    "ComplianceAgent",
    "ComplianceInput",
    "ComplianceOutput",
    "DocumentAgent",
    "DocumentAgentInput",
    "FraudAgent",
    "FraudInput",
    "FraudResult",
    "KycAgent",
    "KycInput",
    "KycResult",
    "LoanAgent",
    "LoanInput",
    "LoanResult",
    "NotificationAgent",
    "NotificationInput",
    "NotificationOutput",
    "OrchestratorAgent",
    "OrchestratorInput",
    "RetrievalAgent",
    "RetrievalInput",
    "RetrievalOutput",
    "SummarizationAgent",
    "SummarizationInput",
    "SummarizationOutput",
    "Transaction",
    "WorkflowPlan",
]
