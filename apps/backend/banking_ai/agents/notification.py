"""Notification agent.

Renders notification payloads (e.g. "your case needs more information",
"a decision was made") deterministically. Actual delivery (email/SMS/push) is a
side-effecting integration handled outside the core agent so the agent stays
pure and testable; the agent returns the rendered channel-ready messages.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent


class NotificationInput(BaseModel):
    template: str  # e.g. "decision", "needs_info"
    recipient: str
    context: dict[str, str] = Field(default_factory=dict)


class RenderedNotification(BaseModel):
    channel: str
    recipient: str
    subject: str
    body: str


class NotificationOutput(BaseModel):
    messages: list[RenderedNotification]


_TEMPLATES: dict[str, tuple[str, str]] = {
    "decision": (
        "Update on your case {reference}",
        "A decision has been recorded for case {reference}: {decision}.",
    ),
    "needs_info": (
        "Action needed on case {reference}",
        "We need additional information for case {reference}: {detail}.",
    ),
    "received": (
        "We received your submission {reference}",
        "Your submission {reference} is being processed. No action is needed yet.",
    ),
}


class NotificationAgent(BaseAgent[NotificationInput, NotificationOutput]):
    name = "notification_agent"

    async def run(self, payload: NotificationInput) -> NotificationOutput:
        subject_tpl, body_tpl = _TEMPLATES.get(payload.template, ("Notification", "{detail}"))
        ctx = {"reference": "-", "decision": "-", "detail": "-", **payload.context}
        subject = _safe_format(subject_tpl, ctx)
        body = _safe_format(body_tpl, ctx)
        return NotificationOutput(
            messages=[
                RenderedNotification(
                    channel="email",
                    recipient=payload.recipient,
                    subject=subject,
                    body=body,
                )
            ]
        )


def _safe_format(template: str, ctx: dict[str, str]) -> str:
    try:
        return template.format(**ctx)
    except (KeyError, IndexError):
        return template
