"""Deterministic, dependency-free provider for local dev and tests.

This is NOT a model. It echoes a structured, deterministic response so the full
platform (API, agents, workflows) is runnable end-to-end without any API key or
local model server. It is selected automatically only when no real provider is
configured, and every response is clearly labelled as coming from ``echo``.
"""

from __future__ import annotations

import json
import time

from banking_ai.ai.providers.base import LLMProvider
from banking_ai.ai.types import CompletionRequest, CompletionResult


class EchoProvider(LLMProvider):
    name = "echo"
    requires_network = False

    @property
    def model(self) -> str:
        return "echo-stub-1"

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        started = time.perf_counter()
        last_user = next(
            (m.content for m in reversed(request.messages) if m.role.value == "user"),
            "",
        )
        if request.json_mode:
            text = json.dumps(
                {
                    "note": "echo provider (no live model configured)",
                    "echo": last_user[:500],
                }
            )
        else:
            text = (
                "[echo provider - no live model configured] "
                f"Received {len(request.messages)} message(s). "
                f"Last user message: {last_user[:300]}"
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=request.estimated_prompt_tokens,
            completion_tokens=max(1, len(text) // 4),
            latency_ms=latency_ms,
        )
