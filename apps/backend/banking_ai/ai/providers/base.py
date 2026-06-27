"""Provider abstraction.

A provider knows how to turn a :class:`CompletionRequest` into a
:class:`CompletionResult`. Providers must be cheap to construct and must raise
:class:`LLMProviderError` (not arbitrary exceptions) on failure so the router
can apply its fallback policy deterministically.
"""

from __future__ import annotations

import abc

from banking_ai.ai.types import CompletionRequest, CompletionResult


class LLMProvider(abc.ABC):
    #: Stable identifier used in logs, policy and ModelCall records.
    name: str
    #: Whether this provider needs outbound network (drives offline fallback).
    requires_network: bool = True

    @property
    @abc.abstractmethod
    def model(self) -> str:
        """Default model identifier for this provider."""

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Best-effort readiness check (config present, endpoint reachable)."""

    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Run a completion. Must raise ``LLMProviderError`` on any failure."""

    async def aclose(self) -> None:  # noqa: B027 - optional override, intentional no-op
        """Release resources (HTTP clients). Optional override."""
