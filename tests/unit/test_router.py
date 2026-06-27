"""Unit tests for the model router and provider factory.

These tests use fake in-process providers so they are deterministic and require
no network (spec section 14: mock external LLM calls).
"""

from __future__ import annotations

import uuid

import pytest

from banking_ai.ai.factory import build_provider, build_router
from banking_ai.ai.providers.base import LLMProvider
from banking_ai.ai.router import InMemoryObserver, ModelRouter
from banking_ai.ai.types import ChatMessage, CompletionRequest, CompletionResult, Role
from banking_ai.core.config import AppEnv, RouterPolicy, Settings
from banking_ai.core.errors import LLMProviderError, ModelRouterError


class FakeProvider(LLMProvider):
    """Configurable provider for exercising router branches."""

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        fail: bool = False,
        requires_network: bool = True,
        text: str = "ok",
    ) -> None:
        self.name = name
        self.requires_network = requires_network
        self._available = available
        self._fail = fail
        self._text = text
        self.calls = 0

    @property
    def model(self) -> str:
        return f"{self.name}-model"

    async def is_available(self) -> bool:
        return self._available

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        if self._fail:
            raise LLMProviderError(f"{self.name} boom", details={"provider": self.name})
        return CompletionResult(
            text=self._text,
            provider=self.name,
            model=self.model,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=1,
        )


def _request() -> CompletionRequest:
    return CompletionRequest(
        messages=[ChatMessage(role=Role.USER, content="hello")],
        prompt_version="v1",
    )


@pytest.mark.asyncio
async def test_primary_success_no_fallback() -> None:
    primary = FakeProvider("groq")
    fallback = FakeProvider("local_gemma")
    observer = InMemoryObserver()
    router = ModelRouter(providers=[primary, fallback], policy="prefer_online", observer=observer)

    result = await router.complete(_request())

    assert result.provider == "groq"
    assert result.used_fallback is False
    assert result.fallback_reason is None
    assert primary.calls == 1
    assert fallback.calls == 0
    # One success record, marked successful.
    assert len(observer.records) == 1
    assert observer.records[0].success is True
    assert observer.records[0].prompt_version == "v1"


@pytest.mark.asyncio
async def test_fallback_on_provider_error() -> None:
    primary = FakeProvider("groq", fail=True)
    fallback = FakeProvider("local_gemma", text="from-fallback")
    observer = InMemoryObserver()
    router = ModelRouter(providers=[primary, fallback], policy="prefer_online", observer=observer)

    result = await router.complete(_request())

    assert result.provider == "local_gemma"
    assert result.text == "from-fallback"
    assert result.used_fallback is True
    assert result.fallback_reason is not None
    assert "groq" in result.fallback_reason
    # Two records: one failure (primary), one success (fallback).
    assert len(observer.records) == 2
    assert observer.records[0].success is False
    assert observer.records[0].provider == "groq"
    assert observer.records[1].success is True
    assert observer.records[1].provider == "local_gemma"
    assert observer.records[1].used_fallback is True


@pytest.mark.asyncio
async def test_fallback_when_primary_unavailable() -> None:
    primary = FakeProvider("groq", available=False)
    fallback = FakeProvider("local_gemma")
    observer = InMemoryObserver()
    router = ModelRouter(providers=[primary, fallback], policy="prefer_online", observer=observer)

    result = await router.complete(_request())

    assert result.provider == "local_gemma"
    assert result.used_fallback is True
    # Primary never actually invoked because it reported unavailable.
    assert primary.calls == 0
    assert observer.records[0].success is False


@pytest.mark.asyncio
async def test_all_providers_fail_raises() -> None:
    primary = FakeProvider("groq", fail=True)
    fallback = FakeProvider("local_gemma", fail=True)
    observer = InMemoryObserver()
    router = ModelRouter(providers=[primary, fallback], policy="prefer_online", observer=observer)

    with pytest.raises(ModelRouterError) as exc_info:
        await router.complete(_request())

    assert "attempts" in exc_info.value.details
    assert len(exc_info.value.details["attempts"]) == 2
    # A failure record per attempt.
    assert len(observer.records) == 2
    assert all(r.success is False for r in observer.records)


@pytest.mark.asyncio
async def test_observer_failure_does_not_break_routing() -> None:
    class ExplodingObserver:
        async def record(self, record: object) -> None:
            raise RuntimeError("telemetry down")

    primary = FakeProvider("groq")
    router = ModelRouter(providers=[primary], policy="online_only", observer=ExplodingObserver())

    result = await router.complete(_request())
    assert result.provider == "groq"


@pytest.mark.asyncio
async def test_agent_run_id_threaded_into_records() -> None:
    primary = FakeProvider("groq")
    observer = InMemoryObserver()
    router = ModelRouter(providers=[primary], policy="online_only", observer=observer)
    run_id = uuid.uuid4()

    await router.complete(_request(), agent_run_id=run_id)
    assert observer.records[0].agent_run_id == run_id


@pytest.mark.asyncio
async def test_cost_estimated_for_known_provider() -> None:
    observer = InMemoryObserver()

    # A provider whose model maps to a priced entry in the cost table.
    class PricedGroq(FakeProvider):
        @property
        def model(self) -> str:
            return "llama-3.1-70b-versatile"

    router = ModelRouter(providers=[PricedGroq("groq")], policy="online_only", observer=observer)
    await router.complete(_request())
    assert observer.records[-1].estimated_cost_usd > 0


def test_router_requires_providers() -> None:
    with pytest.raises(ValueError):
        ModelRouter(providers=[], policy="prefer_online")


# --- Factory tests ---


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": AppEnv.LOCAL,
        "llm_router_policy": RouterPolicy.PREFER_ONLINE,
        "llm_primary_provider": "groq",
        "llm_fallback_provider": "local_gemma",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_factory_prefer_online_local_appends_echo() -> None:
    router = build_router(_settings())
    assert router.provider_names == ["groq", "local_gemma", "echo"]


def test_factory_online_only() -> None:
    router = build_router(_settings(llm_router_policy=RouterPolicy.ONLINE_ONLY))
    assert router.provider_names == ["groq", "echo"]


def test_factory_offline_only() -> None:
    router = build_router(_settings(llm_router_policy=RouterPolicy.OFFLINE_ONLY))
    assert router.provider_names == ["local_gemma", "echo"]


def test_factory_no_echo_outside_local() -> None:
    router = build_router(
        _settings(
            app_env=AppEnv.PRODUCTION,
            security_jwt_secret="a-very-long-production-secret-value-1234567890",
        )
    )
    assert "echo" not in router.provider_names
    assert router.provider_names == ["groq", "local_gemma"]


def test_build_unknown_provider_raises() -> None:
    with pytest.raises(ModelRouterError):
        build_provider("nope", _settings())


def test_build_echo_provider() -> None:
    provider = build_provider("echo", _settings())
    assert provider.name == "echo"
    assert provider.requires_network is False
