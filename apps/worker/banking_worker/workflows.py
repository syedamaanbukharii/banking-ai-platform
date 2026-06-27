"""Temporal workflow and activity definitions (scaffold).

These mirror the in-process plan execution: a workflow asks the orchestrator for
a plan and runs each step as an activity. Activities delegate to the same
:class:`AgentExecutor` used by the in-process path, so the agent logic is not
duplicated. Imports of ``temporalio`` are deferred/guarded so this module can be
imported for documentation/typing even when the dependency is absent.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    from temporalio import activity, workflow

    _TEMPORAL = True
except Exception:  # pragma: no cover
    _TEMPORAL = False


if _TEMPORAL:

    @activity.defn(name="run_agent_step")
    async def run_agent_step(agent_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Activity: run a single agent step via the shared executor."""
        from banking_ai.ai.factory import build_router
        from banking_ai.ai.vector_store import HashingEmbedder, InMemoryVectorStore
        from banking_ai.core.config import get_settings
        from banking_ai.services.agent_executor import AgentExecutor

        settings = get_settings()
        executor = AgentExecutor(
            router=build_router(settings),
            embedder=HashingEmbedder(dimensions=settings.vector_dimensions),
            vector_store=InMemoryVectorStore(),
        )
        outcome = await executor.run_step(agent_name, payload)
        return outcome.model_dump(mode="json")

    @workflow.defn(name="BankingWorkflow")
    class BankingWorkflow:
        @workflow.run
        async def run(self, workflow_type: str, payload: dict[str, Any]) -> dict[str, Any]:
            from datetime import timedelta

            from banking_ai.agents.orchestrator import OrchestratorAgent, OrchestratorInput
            from banking_ai.db.models.enums import WorkflowType

            plan = (
                await OrchestratorAgent().execute(
                    OrchestratorInput(workflow_type=WorkflowType(workflow_type))
                )
            ).output
            assert plan is not None  # nosec B101

            results: dict[str, Any] = {}
            for step in plan.steps:
                results[step.agent] = await workflow.execute_activity(
                    run_agent_step,
                    args=[step.agent, payload],
                    start_to_close_timeout=timedelta(seconds=60),
                )
            return {
                "requires_human_approval": plan.requires_human_approval,
                "results": results,
            }

else:  # pragma: no cover - placeholders when temporalio is unavailable

    async def run_agent_step(agent_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("temporalio is not installed; install the [workflow] extra.")

    class BankingWorkflow:  # type: ignore[no-redef]
        pass
