"""Workflow service — the human-in-the-loop core.

Implements the workflow lifecycle and the approval state machine that enforces
the platform's first principle: *high-risk decisions remain human-approved*.

Lifecycle:
* ``start`` creates a ``workflows`` row, asks the orchestrator for a plan, runs
  each planned agent in-process (recording an ``agent_runs`` row per step), and
  then either completes the workflow (low-risk) or parks it in
  ``AWAITING_APPROVAL`` with a pending ``approvals`` row (high-risk, or when an
  agent itself flagged ``requires_human_review``).
* ``approve`` / ``reject`` / ``escalate`` are guarded transitions that only apply
  to a workflow awaiting approval; each records the decision, the deciding user
  and a reason, and writes an audit log entry.

The in-process executor is the default backend (``WORKFLOW_BACKEND=inprocess``).
A Temporal-backed runner is a documented seam (``apps/worker``) that would drive
the very same agents and approval rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from banking_ai.agents.base import AgentOutcome
from banking_ai.agents.orchestrator import OrchestratorAgent, OrchestratorInput
from banking_ai.core.errors import NotFoundError, WorkflowStateError
from banking_ai.core.logging import get_logger
from banking_ai.db.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
    ApprovalKind,
    WorkflowStatus,
    WorkflowType,
)
from banking_ai.db.models.workflow import AgentRun, Approval, Workflow
from banking_ai.services.agent_executor import AgentExecutor
from banking_ai.services.audit_service import AuditService

logger = get_logger(__name__)

# States from which a human decision is valid.
_DECIDABLE = {WorkflowStatus.AWAITING_APPROVAL, WorkflowStatus.ESCALATED}


class WorkflowService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        executor: AgentExecutor,
        audit: AuditService | None = None,
        orchestrator: OrchestratorAgent | None = None,
    ) -> None:
        self._session = session
        self._executor = executor
        self._audit = audit
        self._orchestrator = orchestrator or OrchestratorAgent()

    async def start(
        self,
        *,
        workflow_type: WorkflowType,
        input_payload: dict[str, object],
        created_by: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> Workflow:
        plan_outcome = await self._orchestrator.execute(
            OrchestratorInput(workflow_type=workflow_type, input_payload=input_payload)
        )
        plan = plan_outcome.output
        assert plan is not None  # nosec B101 - orchestrator plan is total over enum

        workflow = Workflow(
            workflow_type=workflow_type.value,
            status=WorkflowStatus.RUNNING.value,
            input_payload=input_payload,
            requires_human_approval=plan.requires_human_approval,
            created_by=created_by,
        )
        self._session.add(workflow)
        await self._session.flush()

        # Execute planned agent steps in order.
        agent_flagged_review = False
        results: dict[str, object] = {}
        step_payload = {**input_payload, "workflow_id": str(workflow.id)}
        for step in plan.steps:
            run = AgentRun(
                workflow_id=workflow.id,
                agent_name=step.agent,
                status=AgentRunStatus.STARTED.value,
                input=_jsonable(step_payload),
            )
            self._session.add(run)
            await self._session.flush()

            try:
                outcome = await self._executor.run_step(step.agent, step_payload)
            except Exception as exc:
                outcome = AgentOutcome(
                    agent_name=step.agent,
                    status="failed",
                    output=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            run.status = (
                AgentRunStatus.SUCCEEDED.value
                if outcome.status == "succeeded"
                else AgentRunStatus.FAILED.value
            )
            run.output = outcome.output.model_dump(mode="json") if outcome.output else None
            run.error = outcome.error
            run.latency_ms = outcome.latency_ms
            run.prompt_version = outcome.prompt_version
            run.model_used = outcome.model_used
            await self._session.flush()

            if outcome.output is not None:
                results[step.agent] = outcome.output.model_dump(mode="json")
                if bool(getattr(outcome.output, "requires_human_review", False)):
                    agent_flagged_review = True
            if outcome.status == "failed":
                workflow.status = WorkflowStatus.FAILED.value
                workflow.error = outcome.error
                workflow.result = results
                await self._session.flush()
                await self._maybe_audit(
                    action="workflow.failed",
                    workflow=workflow,
                    actor_id=created_by,
                    request_id=request_id,
                    context={"agent": step.agent},
                )
                return await self._reload(workflow.id)

        workflow.result = results
        needs_approval = plan.requires_human_approval or agent_flagged_review

        if needs_approval:
            workflow.status = WorkflowStatus.AWAITING_APPROVAL.value
            self._session.add(
                Approval(
                    workflow_id=workflow.id,
                    kind=ApprovalKind.APPROVAL.value,
                    decision=ApprovalDecision.PENDING.value,
                    required_permission=plan.approval_permission or "workflow:approve",
                    summary=plan.rationale,
                )
            )
            action = "workflow.awaiting_approval"
        else:
            workflow.status = WorkflowStatus.COMPLETED.value
            action = "workflow.completed"

        await self._session.flush()
        await self._maybe_audit(
            action=action,
            workflow=workflow,
            actor_id=created_by,
            request_id=request_id,
            context={"requires_approval": needs_approval},
        )
        logger.info(
            "workflow.started",
            workflow_id=str(workflow.id),
            type=workflow_type.value,
            status=workflow.status,
        )
        return await self._reload(workflow.id)

    async def get(self, workflow_id: uuid.UUID) -> Workflow:
        workflow = await self._reload(workflow_id)
        if workflow is None:
            raise NotFoundError(f"Workflow {workflow_id} not found.")
        return workflow

    async def approve(
        self,
        workflow_id: uuid.UUID,
        *,
        decided_by: uuid.UUID,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> Workflow:
        return await self._decide(
            workflow_id,
            target=WorkflowStatus.APPROVED,
            decision=ApprovalDecision.APPROVED,
            kind=ApprovalKind.APPROVAL,
            decided_by=decided_by,
            reason=reason,
            request_id=request_id,
        )

    async def reject(
        self,
        workflow_id: uuid.UUID,
        *,
        decided_by: uuid.UUID,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> Workflow:
        return await self._decide(
            workflow_id,
            target=WorkflowStatus.REJECTED,
            decision=ApprovalDecision.REJECTED,
            kind=ApprovalKind.REJECTION,
            decided_by=decided_by,
            reason=reason,
            request_id=request_id,
        )

    async def escalate(
        self,
        workflow_id: uuid.UUID,
        *,
        decided_by: uuid.UUID,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> Workflow:
        return await self._decide(
            workflow_id,
            target=WorkflowStatus.ESCALATED,
            decision=ApprovalDecision.ESCALATED,
            kind=ApprovalKind.ESCALATION,
            decided_by=decided_by,
            reason=reason,
            request_id=request_id,
        )

    async def review_queue(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Workflow], int]:
        """Workflows awaiting a human decision (manual-review queue)."""
        statuses = [s.value for s in _DECIDABLE]
        base = select(Workflow).where(Workflow.status.in_(statuses))
        total = len(list((await self._session.execute(base)).scalars().all()))
        rows = (
            (
                await self._session.execute(
                    base.order_by(Workflow.created_at).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    # --- internals ---

    async def _decide(
        self,
        workflow_id: uuid.UUID,
        *,
        target: WorkflowStatus,
        decision: ApprovalDecision,
        kind: ApprovalKind,
        decided_by: uuid.UUID,
        reason: str | None,
        request_id: str | None,
    ) -> Workflow:
        workflow = await self.get(workflow_id)
        current = WorkflowStatus(workflow.status)
        if current not in _DECIDABLE:
            raise WorkflowStateError(
                f"Workflow {workflow_id} is '{current.value}', not awaiting a decision.",
                details={"current_status": current.value},
            )

        # Update the pending approval (or add a decision record if none pending).
        pending = next(
            (a for a in workflow.approvals if a.decision == ApprovalDecision.PENDING.value),
            None,
        )
        if pending is None:
            pending = Approval(
                workflow_id=workflow.id,
                kind=kind.value,
                required_permission="workflow:approve",
            )
            self._session.add(pending)
        pending.decision = decision.value
        pending.kind = kind.value
        pending.decided_by = decided_by
        pending.decision_reason = reason

        workflow.status = target.value
        # Approval completes the workflow; rejection/escalation are terminal-for-now.
        if target is WorkflowStatus.APPROVED:
            workflow.status = WorkflowStatus.COMPLETED.value

        await self._session.flush()
        await self._maybe_audit(
            action=f"workflow.{decision.value}",
            workflow=workflow,
            actor_id=decided_by,
            request_id=request_id,
            context={"reason": reason or ""},
        )
        logger.info(
            "workflow.decision",
            workflow_id=str(workflow.id),
            decision=decision.value,
            final_status=workflow.status,
        )
        return await self._reload(workflow.id)

    async def _reload(self, workflow_id: uuid.UUID) -> Workflow:
        result = await self._session.execute(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(
                selectinload(Workflow.agent_runs),
                selectinload(Workflow.approvals),
                selectinload(Workflow.tasks),
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise NotFoundError(f"Workflow {workflow_id} not found.")
        return workflow

    async def _maybe_audit(
        self,
        *,
        action: str,
        workflow: Workflow,
        actor_id: uuid.UUID | None,
        request_id: str | None,
        context: dict[str, object],
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            action=action,
            resource_type="workflow",
            resource_id=str(workflow.id),
            actor_id=actor_id,
            request_id=request_id,
            context=context,
        )


def _jsonable(payload: dict[str, object]) -> dict[str, object]:
    """Best-effort conversion of payload values to JSON-serialisable forms."""
    out: dict[str, object] = {}
    for key, value in payload.items():
        out[key] = value if _is_jsonable(value) else str(value)
    return out


def _is_jsonable(value: object) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))
