"""Workflow domain models: applications, workflows, agent runs, approvals, tasks."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from banking_ai.db.base import Base, TimestampMixin, UUIDMixin
from banking_ai.db.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
    ApprovalKind,
    TaskState,
    WorkflowStatus,
    WorkflowType,
)


class Application(UUIDMixin, TimestampMixin, Base):
    """A business case (e.g. a loan application or KYC case) a workflow acts on."""

    __tablename__ = "applications"

    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    workflows: Mapped[list[Workflow]] = relationship(back_populates="application")


class Workflow(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workflows"

    workflow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=WorkflowStatus.PENDING, nullable=False, index=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL")
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    # External orchestrator handle (e.g. Temporal workflow id) when applicable.
    external_run_id: Mapped[str | None] = mapped_column(String(255), index=True)
    requires_human_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    application: Mapped[Application | None] = relationship(back_populates="workflows")
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[TaskStatus]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class AgentRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=AgentRunStatus.STARTED, nullable=False)
    input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model_used: Mapped[str | None] = mapped_column(String(128))

    workflow: Mapped[Workflow | None] = relationship(back_populates="agent_runs")


class Approval(UUIDMixin, TimestampMixin, Base):
    """A human-in-the-loop decision point (spec section 10)."""

    __tablename__ = "approvals"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default=ApprovalKind.APPROVAL, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(32), default=ApprovalDecision.PENDING, nullable=False, index=True
    )
    required_permission: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)

    workflow: Mapped[Workflow] = relationship(back_populates="approvals")


class TaskStatus(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task_status"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default=TaskState.QUEUED, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    workflow: Mapped[Workflow] = relationship(back_populates="tasks")


__all__ = [
    "AgentRun",
    "Application",
    "Approval",
    "TaskStatus",
    "Workflow",
    "WorkflowType",
]
