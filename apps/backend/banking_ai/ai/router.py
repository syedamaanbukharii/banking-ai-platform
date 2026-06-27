"""Model router.

Responsibilities (spec section 7):
* decide which model to use (an explicit, ordered provider chain),
* fall back when a provider is unavailable (e.g. no internet),
* log the model used and the reason for any fallback,
* keep the selection policy explicit and auditable,
* never silently switch models without traceability.

The router emits one :class:`ModelCallRecord` per *attempt* (including failed
ones) to its observer, so the audit trail captures exactly what happened and
why a fallback occurred. The DB-backed observer persists these to
``model_calls`` / ``cost_tracking``.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from banking_ai.ai.cost import estimate_cost_usd
from banking_ai.ai.providers.base import LLMProvider
from banking_ai.ai.types import CompletionRequest, CompletionResult
from banking_ai.core.errors import LLMProviderError, ModelRouterError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)


class ModelCallRecord(BaseModel):
    provider: str
    model: str
    routing_policy: str
    used_fallback: bool
    fallback_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    success: bool
    error: str | None
    prompt_version: str | None
    estimated_cost_usd: float
    agent_run_id: uuid.UUID | None = None


@runtime_checkable
class RouterObserver(Protocol):
    """Sink for routing telemetry. Implementations must not raise."""

    async def record(self, record: ModelCallRecord) -> None: ...


class NullObserver:
    async def record(self, record: ModelCallRecord) -> None:
        return None


class InMemoryObserver:
    """Collects records in memory (used by tests and the echo/dev path)."""

    def __init__(self) -> None:
        self.records: list[ModelCallRecord] = []

    async def record(self, record: ModelCallRecord) -> None:
        self.records.append(record)


class ModelRouter:
    def __init__(
        self,
        *,
        providers: list[LLMProvider],
        policy: str,
        observer: RouterObserver | None = None,
    ) -> None:
        if not providers:
            raise ValueError("ModelRouter requires at least one provider.")
        self._providers = providers
        self._policy = policy
        self._observer: RouterObserver = observer or NullObserver()

    @property
    def policy(self) -> str:
        return self._policy

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def complete(
        self,
        request: CompletionRequest,
        *,
        agent_run_id: uuid.UUID | None = None,
    ) -> CompletionResult:
        """Run a completion, trying providers in order until one succeeds."""
        attempts: list[str] = []
        previous_error: str | None = None

        for index, provider in enumerate(self._providers):
            used_fallback = index > 0
            try:
                available = await provider.is_available()
            except Exception:
                available = False

            if not available:
                reason = f"{provider.name} reported unavailable"
                previous_error = reason
                attempts.append(reason)
                await self._emit_failure(
                    provider, request, used_fallback, reason, agent_run_id, latency_ms=0
                )
                logger.warning("router.provider_unavailable", provider=provider.name)
                continue

            try:
                result = await provider.complete(request)
            except LLMProviderError as exc:
                previous_error = exc.message
                attempts.append(f"{provider.name}: {exc.message}")
                await self._emit_failure(
                    provider, request, used_fallback, exc.message, agent_run_id, latency_ms=0
                )
                logger.warning("router.provider_failed", provider=provider.name, reason=exc.message)
                continue

            # Success — annotate fallback metadata and record telemetry.
            result.used_fallback = used_fallback
            result.fallback_reason = previous_error if used_fallback else None
            await self._emit_success(result, request, agent_run_id)
            logger.info(
                "router.completed",
                provider=result.provider,
                model=result.model,
                used_fallback=result.used_fallback,
                fallback_reason=result.fallback_reason,
                policy=self._policy,
            )
            return result

        logger.error("router.exhausted", policy=self._policy, attempts=attempts)
        raise ModelRouterError(
            "All configured LLM providers failed.",
            details={"policy": self._policy, "attempts": attempts},
        )

    async def _emit_success(
        self,
        result: CompletionResult,
        request: CompletionRequest,
        agent_run_id: uuid.UUID | None,
    ) -> None:
        record = ModelCallRecord(
            provider=result.provider,
            model=result.model,
            routing_policy=self._policy,
            used_fallback=result.used_fallback,
            fallback_reason=result.fallback_reason,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
            success=True,
            error=None,
            prompt_version=request.prompt_version,
            estimated_cost_usd=estimate_cost_usd(
                provider=result.provider,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            ),
            agent_run_id=agent_run_id,
        )
        await self._safe_record(record)

    async def _emit_failure(
        self,
        provider: LLMProvider,
        request: CompletionRequest,
        used_fallback: bool,
        error: str,
        agent_run_id: uuid.UUID | None,
        *,
        latency_ms: int,
    ) -> None:
        record = ModelCallRecord(
            provider=provider.name,
            model=provider.model,
            routing_policy=self._policy,
            used_fallback=used_fallback,
            fallback_reason=None,
            prompt_tokens=request.estimated_prompt_tokens,
            completion_tokens=0,
            latency_ms=latency_ms,
            success=False,
            error=error,
            prompt_version=request.prompt_version,
            estimated_cost_usd=0.0,
            agent_run_id=agent_run_id,
        )
        await self._safe_record(record)

    async def _safe_record(self, record: ModelCallRecord) -> None:
        try:
            await self._observer.record(record)
        except Exception:
            logger.warning("router.observer_failed", provider=record.provider)

    async def aclose(self) -> None:
        for provider in self._providers:
            await provider.aclose()
