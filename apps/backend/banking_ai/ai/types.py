"""Typed contracts for LLM interactions.

These Pydantic models are the stable interface between agents, the router and
providers. Providers translate to/from their wire formats; everything above the
provider boundary speaks only these types.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: Role
    content: str


class CompletionRequest(BaseModel):
    messages: list[ChatMessage]
    max_tokens: int = Field(default=1024, ge=1, le=32_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # Optional JSON-mode hint; providers that support it will request structured
    # output (spec: prefer structured outputs for downstream logic).
    json_mode: bool = False
    # Traceability metadata flowed through to ModelCall records.
    prompt_version: str | None = None

    @property
    def estimated_prompt_tokens(self) -> int:
        # Cheap heuristic (~4 chars/token); good enough for cost estimation.
        chars = sum(len(m.content) for m in self.messages)
        return max(1, chars // 4)


class CompletionResult(BaseModel):
    text: str
    provider: str
    model: str
    used_fallback: bool = False
    fallback_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
