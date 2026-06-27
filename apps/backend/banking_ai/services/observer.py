"""Database-backed router observer.

Persists every :class:`ModelCallRecord` emitted by the router into ``model_calls``
and, for successful priced calls, a matching ``cost_tracking`` row. This is the
production sink that makes model usage fully auditable (spec section 7 & 15).

It commits in its own short-lived session so telemetry is durable even if the
surrounding request later fails — and, per the router contract, it must never
raise back into routing (the router wraps ``record`` in a guard, and we also
swallow/log here).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from banking_ai.ai.router import ModelCallRecord
from banking_ai.core.logging import get_logger
from banking_ai.db.models.observability import CostTracking, ModelCall

logger = get_logger(__name__)


class DbRouterObserver:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def record(self, record: ModelCallRecord) -> None:
        try:
            async with self._sessionmaker() as session:
                call = ModelCall(
                    agent_run_id=record.agent_run_id,
                    provider=record.provider,
                    model=record.model,
                    routing_policy=record.routing_policy,
                    used_fallback=record.used_fallback,
                    fallback_reason=record.fallback_reason,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    latency_ms=record.latency_ms,
                    success=record.success,
                    error=record.error,
                    prompt_version=record.prompt_version,
                )
                session.add(call)
                await session.flush()

                if record.success and record.estimated_cost_usd > 0:
                    session.add(
                        CostTracking(
                            model_call_id=call.id,
                            provider=record.provider,
                            model=record.model,
                            total_tokens=record.prompt_tokens + record.completion_tokens,
                            estimated_cost_usd=record.estimated_cost_usd,
                        )
                    )
                await session.commit()
        except Exception:
            logger.warning("observer.persist_failed", provider=record.provider)
