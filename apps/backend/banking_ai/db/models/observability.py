"""Observability & governance models.

``audit_logs`` are treated as append-only: the service layer never updates or
deletes rows, and the table exposes no ORM relationships that would cascade a
delete into it. (DB-level immutability via triggers/grants is an environment
hardening step documented in docs/security.md.)
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from banking_ai.db.base import Base, TimestampMixin, UUIDMixin
from banking_ai.db.models.enums import IncidentSeverity, IncidentStatus


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Non-sensitive context only; redaction happens before write.
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ModelCall(UUIDMixin, TimestampMixin, Base):
    """Traceability for every LLM call routed through the model router."""

    __tablename__ = "model_calls"

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    routing_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(255))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(64))


class CostTracking(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cost_tracking"

    model_call_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_calls.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class Feedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # -1, 0, +1
    comment: Mapped[str | None] = mapped_column(Text)


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default=IncidentSeverity.SEV3, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=IncidentStatus.OPEN, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


__all__ = ["AuditLog", "CostTracking", "Feedback", "Incident", "ModelCall"]
