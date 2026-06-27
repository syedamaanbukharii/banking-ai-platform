"""Groq provider (online primary). OpenAI-compatible API."""

from __future__ import annotations

from banking_ai.ai.providers.openai_compatible import OpenAICompatibleProvider
from banking_ai.core.config import Settings


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            name="groq",
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            api_key=settings.groq_api_key or None,
            timeout=settings.llm_request_timeout_seconds,
            max_retries=settings.llm_max_retries,
            requires_network=True,
        )
