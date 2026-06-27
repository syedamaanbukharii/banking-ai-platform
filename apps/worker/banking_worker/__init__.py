"""Banking AI Temporal worker (production workflow backend seam).

The default deployment runs workflows in-process (``WORKFLOW_BACKEND=inprocess``)
via :class:`banking_ai.services.workflow_service.WorkflowService`. This package
is the seam for running the same orchestration under a Temporal cluster
(``WORKFLOW_BACKEND=temporal``); it is intentionally a thin, documented scaffold
rather than a second full implementation.
"""
