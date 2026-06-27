"""Versioned prompt registry.

Prompts are versioned artifacts: each agent references a specific version string
(e.g. ``summarize.v1``) which flows into ``agent_runs.prompt_version`` and the
``model_calls`` records, so any model output can be traced back to the exact
prompt that produced it. Templates live as files under ``templates/`` and are
loaded once at import.

Changing a prompt means adding a new versioned file (``*.v2.md``) and pointing
the agent at it — old runs remain attributable to the old version.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptNotFoundError(KeyError):
    """Raised when a requested prompt version has no template file."""


@lru_cache
def get_prompt(version: str) -> str:
    """Return the prompt text for a version (e.g. ``"summarize.v1"``)."""
    path = _TEMPLATE_DIR / f"{version}.md"
    if not path.exists():
        raise PromptNotFoundError(version)
    return path.read_text(encoding="utf-8").strip()


def available_versions() -> list[str]:
    return sorted(p.stem for p in _TEMPLATE_DIR.glob("*.md"))


__all__ = ["PromptNotFoundError", "available_versions", "get_prompt"]
