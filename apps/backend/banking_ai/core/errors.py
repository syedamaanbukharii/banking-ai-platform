"""Application error hierarchy.

Every error carries a stable, machine-readable ``code`` and an HTTP status.
The API layer renders these into a consistent error envelope so clients can
branch on ``code`` rather than parsing prose (spec: "return structured errors").
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected application errors."""

    code: str = "app_error"
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationAppError(AppError):
    code = "validation_error"
    status_code = 422
    message = "Request validation failed."


class AuthenticationError(AppError):
    code = "authentication_error"
    status_code = 401
    message = "Authentication required or failed."


class AuthorizationError(AppError):
    code = "authorization_error"
    status_code = 403
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    message = "Resource not found."


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    message = "The request conflicts with the current state."


class RateLimitError(AppError):
    code = "rate_limited"
    status_code = 429
    message = "Too many requests."


class WorkflowStateError(ConflictError):
    code = "invalid_workflow_state"
    message = "The workflow is not in a state that allows this transition."


class LLMProviderError(AppError):
    """A specific LLM provider failed (network, auth, timeout, bad response)."""

    code = "llm_provider_error"
    status_code = 502
    message = "An LLM provider call failed."


class ModelRouterError(AppError):
    """The router exhausted all configured providers."""

    code = "model_router_error"
    status_code = 503
    message = "No LLM provider was able to serve the request."


class AgentError(AppError):
    code = "agent_error"
    status_code = 500
    message = "An agent failed to complete its task."
