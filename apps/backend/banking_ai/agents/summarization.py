"""Summarization agent.

The one agent here whose core output comes from a language model. It builds a
strict prompt, calls the model router (which handles provider selection and
fallback), and returns the text plus the model that produced it. In tests the
router is constructed with a fake/echo provider, so no network is required and
behaviour is deterministic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.ai.types import ChatMessage, CompletionRequest, Role
from banking_ai.prompts import get_prompt

PROMPT_VERSION = "summarize.v1"

_SYSTEM = get_prompt(PROMPT_VERSION)


class SummarizationInput(BaseModel):
    content: str
    max_sentences: int = Field(default=5, ge=1, le=20)


class SummarizationOutput(BaseModel):
    summary: str
    model_used: str
    used_fallback: bool


class SummarizationAgent(BaseAgent[SummarizationInput, SummarizationOutput]):
    name = "summarization_agent"
    prompt_version = PROMPT_VERSION

    async def run(self, payload: SummarizationInput) -> SummarizationOutput:
        request = CompletionRequest(
            messages=[
                ChatMessage(role=Role.SYSTEM, content=_SYSTEM),
                ChatMessage(
                    role=Role.USER,
                    content=(
                        f"Summarize the following in at most {payload.max_sentences} "
                        f"sentences:\n\n{payload.content}"
                    ),
                ),
            ],
            max_tokens=512,
            temperature=0.1,
            prompt_version=self.prompt_version,
        )
        result = await self.router.complete(request)
        return SummarizationOutput(
            summary=result.text.strip(),
            model_used=f"{result.provider}:{result.model}",
            used_fallback=result.used_fallback,
        )
