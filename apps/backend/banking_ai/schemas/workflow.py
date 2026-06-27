"""Workflow schemas: start, read, and nested agent-run / task views."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from banking_ai.db.models.enums import (
    AgentRunStatus,
    TaskState,
    WorkflowStatus,
    WorkflowType,
)
from banking_ai.schemas.common import ApiModel


class WorkflowStartRequest(ApiModel):
    workflow_type: WorkflowType
    input_payload: dict[str, object] = Field(default_factory=dict)
    application_reference: str | None = Field(default=None, max_length=64)


class AgentRunOut(ApiModel):
    id: uuid.UUID
    agent_name: str
    status: AgentRunStatus
    input: dict[str, object]
    output: dict[str, object] | None
    error: str | None
    latency_ms: int | None
    prompt_version: str | None
    model_used: str | None
    created_at: datetime


class TaskOut(ApiModel):
    id: uuid.UUID
    name: str
    state: TaskState
    detail: str | None
    progress: float


class ApprovalOut(ApiModel):
    id: uuid.UUID
    kind: str
    decision: str
    required_permission: str
    summary: str | None
    decided_by: uuid.UUID | None
    decision_reason: str | None
    created_at: datetime


class WorkflowOut(ApiModel):
    id: uuid.UUID
    workflow_type: WorkflowType
    status: WorkflowStatus
    application_id: uuid.UUID | None
    input_payload: dict[str, object]
    result: dict[str, object] | None
    error: str | None
    requires_human_approval: bool
    created_at: datetime
    updated_at: datetime


class WorkflowDetail(WorkflowOut):
    agent_runs: list[AgentRunOut] = Field(default_factory=list)
    approvals: list[ApprovalOut] = Field(default_factory=list)
    tasks: list[TaskOut] = Field(default_factory=list)
