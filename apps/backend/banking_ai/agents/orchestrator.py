"""Orchestrator agent.

The orchestrator does not itself call models; it decides *which* specialised
agents handle a workflow and whether the workflow must pause for human approval
(spec: orchestrator + HITL). Keeping the plan explicit and data-driven makes the
control flow auditable and testable. The workflow service consumes this plan to
drive execution (in-process today, Temporal in production).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.core.rbac import Permission
from banking_ai.db.models.enums import WorkflowType


class PlanStep(BaseModel):
    agent: str
    description: str


class WorkflowPlan(BaseModel):
    workflow_type: WorkflowType
    steps: list[PlanStep]
    requires_human_approval: bool
    approval_permission: str | None = None
    rationale: str


class OrchestratorInput(BaseModel):
    workflow_type: WorkflowType
    input_payload: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _PlanSpec:
    steps: tuple[tuple[str, str], ...]
    requires_human_approval: bool
    approval_permission: str | None


# Static plans per workflow type. Human-approval gates and the permission a
# reviewer must hold are explicit and align with the RBAC model.
_PLANS: dict[WorkflowType, _PlanSpec] = {
    WorkflowType.DOCUMENT_INTELLIGENCE: _PlanSpec(
        steps=(
            ("document_agent", "Extract and validate document fields."),
            ("summarization_agent", "Summarize the document for a reviewer."),
        ),
        requires_human_approval=False,
        approval_permission=None,
    ),
    WorkflowType.KYC: _PlanSpec(
        steps=(
            ("document_agent", "Extract identity document fields."),
            ("kyc_agent", "Run completeness, consistency and risk checks."),
        ),
        requires_human_approval=True,
        approval_permission=Permission.KYC_REVIEW.value,
    ),
    WorkflowType.FRAUD_REVIEW: _PlanSpec(
        steps=(("fraud_agent", "Score transaction risk with explainable signals."),),
        requires_human_approval=True,
        approval_permission=Permission.FRAUD_REVIEW.value,
    ),
    WorkflowType.COMPLIANCE: _PlanSpec(
        steps=(
            ("retrieval_agent", "Retrieve relevant policy excerpts."),
            ("compliance_agent", "Compose a grounded, cited answer."),
        ),
        requires_human_approval=False,
        approval_permission=None,
    ),
    WorkflowType.AUDIT_EVIDENCE: _PlanSpec(
        steps=(("audit_agent", "Assemble an immutable evidence bundle."),),
        requires_human_approval=False,
        approval_permission=None,
    ),
    WorkflowType.LOAN: _PlanSpec(
        steps=(
            ("document_agent", "Validate submitted loan documents."),
            ("loan_agent", "Compute affordability and a recommendation."),
        ),
        requires_human_approval=True,
        approval_permission=Permission.LOAN_PROCESS.value,
    ),
}


class OrchestratorAgent(BaseAgent[OrchestratorInput, WorkflowPlan]):
    name = "orchestrator_agent"

    async def run(self, payload: OrchestratorInput) -> WorkflowPlan:
        spec = _PLANS[payload.workflow_type]
        steps = [PlanStep(agent=a, description=d) for a, d in spec.steps]
        rationale = (
            "High-risk workflow: routed through a human approval gate."
            if spec.requires_human_approval
            else "Low-risk workflow: fully automated with full audit logging."
        )
        return WorkflowPlan(
            workflow_type=payload.workflow_type,
            steps=steps,
            requires_human_approval=spec.requires_human_approval,
            approval_permission=spec.approval_permission,
            rationale=rationale,
        )
