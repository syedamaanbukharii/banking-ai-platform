"""Local Gemma-compatible provider (offline fallback).

Targets any OpenAI-compatible local server (Ollama, vLLM, llama.cpp server).
``requires_network=False`` marks it as the offline-capable option the router
prefers when connectivity is unavailable.
"""

from __future__ import annotations

from banking_ai.ai.providers.openai_compatible import OpenAICompatibleProvider
from banking_ai.core.config import Settings


class LocalGemmaProvider(OpenAICompatibleProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            name="local_gemma",
            base_url=settings.local_gemma_base_url,
            model=settings.local_gemma_model,
            api_key=None,
            timeout=settings.llm_request_timeout_seconds,
            max_retries=settings.llm_max_retries,
            requires_network=False,
        )
