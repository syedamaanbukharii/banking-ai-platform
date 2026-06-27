"""Agent foundation.

Every agent has a single clear responsibility, accepts a typed input model,
returns a typed output model, logs its actions, and is independently testable
(spec section 9). Agents that call an LLM do so through the injected
:class:`ModelRouter`; their *deterministic* logic (validation, scoring, field
extraction) does not depend on any model and is therefore fully unit-testable
without network access.

``BaseAgent.execute`` wraps ``run`` with timing and structured logging and
returns an :class:`AgentOutcome` capturing status, latency and the model used.
Persistence of ``agent_runs`` rows is handled by the service layer, which calls
agents via this uniform contract.
"""

from __future__ import annotations

import abc
import time
from typing import Generic, TypeVar

from pydantic import BaseModel

from banking_ai.ai.router import ModelRouter
from banking_ai.core.errors import AgentError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class AgentOutcome(BaseModel, Generic[TOutput]):
    agent_name: str
    status: str  # "succeeded" | "failed"
    output: TOutput | None
    error: str | None = None
    latency_ms: int = 0
    model_used: str | None = None
    prompt_version: str | None = None


class BaseAgent(abc.ABC, Generic[TInput, TOutput]):
    #: Stable identifier used for logging and the ``agent_runs.agent_name`` column.
    name: str
    #: Prompt template version for traceability (overridden by LLM agents).
    prompt_version: str | None = None

    def __init__(self, router: ModelRouter | None = None) -> None:
        self._router = router

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            raise AgentError(f"Agent '{self.name}' requires a model router but none was provided.")
        return self._router

    @abc.abstractmethod
    async def run(self, payload: TInput) -> TOutput:
        """Core logic. Implementations should be deterministic where possible."""

    async def execute(self, payload: TInput) -> AgentOutcome[TOutput]:
        """Run the agent with timing, logging and uniform error handling."""
        started = time.perf_counter()
        logger.info("agent.started", agent=self.name)
        try:
            output = await self.run(payload)
        except AgentError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("agent.failed", agent=self.name, reason=exc.message)
            return AgentOutcome(
                agent_name=self.name,
                status="failed",
                output=None,
                error=exc.message,
                latency_ms=latency_ms,
                prompt_version=self.prompt_version,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error("agent.crashed", agent=self.name, error=type(exc).__name__)
            return AgentOutcome(
                agent_name=self.name,
                status="failed",
                output=None,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
                prompt_version=self.prompt_version,
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info("agent.succeeded", agent=self.name, latency_ms=latency_ms)
        return AgentOutcome(
            agent_name=self.name,
            status="succeeded",
            output=output,
            latency_ms=latency_ms,
            prompt_version=self.prompt_version,
        )
