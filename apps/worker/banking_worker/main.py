"""Temporal worker entrypoint (scaffold).

When ``WORKFLOW_BACKEND=temporal`` and the optional ``temporalio`` dependency is
installed, this would connect to the Temporal frontend, register the workflow
and activity definitions, and poll the task queue. The activities are thin
wrappers around the existing agents/services, so the *business logic is shared*
with the in-process executor — Temporal only changes durability/orchestration.

To keep the repository runnable without a Temporal cluster, this entrypoint:
* logs and exits cleanly if the backend is not ``temporal``; and
* logs a clear message if ``temporalio`` is not installed (the ``[workflow]``
  extra provides it).

See docs/deployment.md ("Workflow engine") for the production wiring.
"""

from __future__ import annotations

import asyncio

from banking_ai.core.config import WorkflowBackend, get_settings
from banking_ai.core.logging import configure_logging, get_logger

logger = get_logger("banking_worker")


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.app_log_level, json_logs=settings.app_log_json)

    if settings.workflow_backend is not WorkflowBackend.TEMPORAL:
        logger.info(
            "worker.disabled",
            reason="WORKFLOW_BACKEND is not 'temporal'; workflows run in-process.",
            backend=settings.workflow_backend.value,
        )
        return

    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except Exception:  # pragma: no cover - optional dependency
        logger.error(
            "worker.dependency_missing",
            hint="Install the [workflow] extra (temporalio) to run the Temporal worker.",
        )
        return

    from banking_worker.workflows import BankingWorkflow, run_agent_step

    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    logger.info(
        "worker.starting",
        host=settings.temporal_host,
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[BankingWorkflow],
        activities=[run_agent_step],
    )
    await worker.run()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
