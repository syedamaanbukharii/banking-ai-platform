"""Construction of providers and the router from settings.

The factory is the single place that turns configuration (``llm_router_policy``
and the provider settings) into an ordered provider chain. Keeping this logic in
one function makes the routing policy explicit and auditable (spec section 7).

Policy -> chain:
* ``online_only``   -> [primary]
* ``offline_only``  -> [fallback]
* ``prefer_online`` -> [primary, fallback]

In **local** environments only, a deterministic :class:`EchoProvider` is appended
as a last resort so the platform is runnable end-to-end with zero API keys. It is
never appended outside local dev, so production can never silently serve a stub
response in place of a real model.
"""

from __future__ import annotations

from banking_ai.ai.providers.base import LLMProvider
from banking_ai.ai.providers.echo import EchoProvider
from banking_ai.ai.providers.groq import GroqProvider
from banking_ai.ai.providers.local_gemma import LocalGemmaProvider
from banking_ai.ai.router import ModelRouter, RouterObserver
from banking_ai.core.config import AppEnv, RouterPolicy, Settings
from banking_ai.core.errors import ModelRouterError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)

_BUILDERS = {
    "groq": GroqProvider,
    "local_gemma": LocalGemmaProvider,
    "echo": EchoProvider,
}


def build_provider(name: str, settings: Settings) -> LLMProvider:
    """Construct a single named provider."""
    if name == "echo":
        return EchoProvider()
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ModelRouterError(
            f"Unknown LLM provider '{name}'.",
            details={"known": sorted(_BUILDERS)},
        )
    return builder(settings)


def _chain_names(settings: Settings) -> list[str]:
    primary = settings.llm_primary_provider
    fallback = settings.llm_fallback_provider
    policy = settings.llm_router_policy

    if policy is RouterPolicy.ONLINE_ONLY:
        names = [primary]
    elif policy is RouterPolicy.OFFLINE_ONLY:
        names = [fallback]
    else:  # PREFER_ONLINE
        names = [primary, fallback]

    # Local-only safety net so the stack runs without any credentials.
    if settings.app_env is AppEnv.LOCAL and "echo" not in names:
        names.append("echo")
    return names


def build_router(
    settings: Settings,
    *,
    observer: RouterObserver | None = None,
) -> ModelRouter:
    """Build a :class:`ModelRouter` with an ordered chain derived from policy."""
    names = _chain_names(settings)
    providers = [build_provider(name, settings) for name in names]
    logger.info(
        "router.configured",
        policy=settings.llm_router_policy.value,
        providers=[p.name for p in providers],
        env=settings.app_env.value,
    )
    return ModelRouter(
        providers=providers,
        policy=settings.llm_router_policy.value,
        observer=observer,
    )
