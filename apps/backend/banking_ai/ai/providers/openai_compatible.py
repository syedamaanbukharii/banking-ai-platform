"""OpenAI-compatible chat-completions provider.

Both Groq and typical local servers (Ollama, vLLM, llama.cpp) expose the OpenAI
``/chat/completions`` schema, so a single HTTP implementation backs both. The
concrete providers in this package are thin subclasses that supply identity and
configuration.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from banking_ai.ai.providers.base import LLMProvider
from banking_ai.ai.types import CompletionRequest, CompletionResult
from banking_ai.core.errors import LLMProviderError
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)

# Transient HTTP failures worth a quick retry before the router falls back.
_RETRYABLE = (httpx.TimeoutException, httpx.TransportError)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        requires_network: bool = True,
    ) -> None:
        self.name = name
        self.requires_network = requires_network
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max(0, max_retries)

    @property
    def model(self) -> str:
        return self._model

    async def is_available(self) -> bool:
        # Network probes can be slow/flaky; rely on credentials presence here and
        # let ``complete`` surface real connectivity failures to the router.
        if self.requires_network and self._api_key is not None:
            return bool(self._api_key)
        return True

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        started = time.perf_counter()

        @retry(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.2, max=2.0),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(request),
                )

        try:
            response = await _do()
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"{self.name} returned HTTP {exc.response.status_code}.",
                details={"provider": self.name, "status": exc.response.status_code},
            ) from exc
        except _RETRYABLE as exc:
            # Connectivity/timeout — signals the router to consider fallback.
            raise LLMProviderError(
                f"{self.name} is unreachable: {type(exc).__name__}.",
                details={"provider": self.name, "connectivity": True},
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                f"{self.name} call failed: {type(exc).__name__}.",
                details={"provider": self.name},
            ) from exc

        try:
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                f"{self.name} returned an unexpected response shape.",
                details={"provider": self.name},
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self._model,
            prompt_tokens=int(usage.get("prompt_tokens", request.estimated_prompt_tokens)),
            completion_tokens=int(usage.get("completion_tokens", max(1, len(text) // 4))),
            latency_ms=latency_ms,
        )
