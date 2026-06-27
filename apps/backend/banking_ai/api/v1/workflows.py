"""Workflow endpoints — including the human-in-the-loop decision actions."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from banking_ai.api.deps import SessionDep, StateDep, require_permissions
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal
from banking_ai.schemas.audit import ApprovalDecisionRequest
from banking_ai.schemas.common import ErrorResponse, Page
from banking_ai.schemas.workflow import (
    WorkflowDetail,
    WorkflowOut,
    WorkflowStartRequest,
)
from banking_ai.services.agent_executor import AgentExecutor
from banking_ai.services.audit_service import AuditService
from banking_ai.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


def _service(session: SessionDep, state: StateDep) -> WorkflowService:
    executor = AgentExecutor(
        router=state.router,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )
    return WorkflowService(session, executor=executor, audit=AuditService(session))


@router.post("/start", response_model=WorkflowDetail, status_code=201, responses=_ERRORS)
async def start_workflow(
    payload: WorkflowStartRequest,
    request: Request,
    session: SessionDep,
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_START.value)),
) -> WorkflowDetail:
    service = _service(session, state)
    workflow = await service.start(
        workflow_type=payload.workflow_type,
        input_payload=payload.input_payload,
        created_by=uuid.UUID(principal.user_id),
        request_id=getattr(request.state, "request_id", None),
    )
    return WorkflowDetail.model_validate(workflow)


@router.get("", response_model=Page[WorkflowOut])
async def review_queue(
    session: SessionDep,
    state: StateDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_READ.value)),
) -> Page[WorkflowOut]:
    service = _service(session, state)
    rows, total = await service.review_queue(limit=page_size, offset=(page - 1) * page_size)
    items = [WorkflowOut.model_validate(r) for r in rows]
    return Page.build(items, page=page, page_size=page_size, total=total)


@router.get("/{workflow_id}", response_model=WorkflowDetail, responses=_ERRORS)
async def get_workflow(
    workflow_id: uuid.UUID,
    session: SessionDep,
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_READ.value)),
) -> WorkflowDetail:
    service = _service(session, state)
    workflow = await service.get(workflow_id)
    return WorkflowDetail.model_validate(workflow)


@router.post("/{workflow_id}/approve", response_model=WorkflowDetail, responses=_ERRORS)
async def approve_workflow(
    workflow_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: SessionDep,
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_APPROVE.value)),
) -> WorkflowDetail:
    service = _service(session, state)
    workflow = await service.approve(
        workflow_id,
        decided_by=uuid.UUID(principal.user_id),
        reason=payload.reason,
        request_id=getattr(request.state, "request_id", None),
    )
    return WorkflowDetail.model_validate(workflow)


@router.post("/{workflow_id}/reject", response_model=WorkflowDetail, responses=_ERRORS)
async def reject_workflow(
    workflow_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: SessionDep,
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_REJECT.value)),
) -> WorkflowDetail:
    service = _service(session, state)
    workflow = await service.reject(
        workflow_id,
        decided_by=uuid.UUID(principal.user_id),
        reason=payload.reason,
        request_id=getattr(request.state, "request_id", None),
    )
    return WorkflowDetail.model_validate(workflow)


@router.post("/{workflow_id}/escalate", response_model=WorkflowDetail, responses=_ERRORS)
async def escalate_workflow(
    workflow_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: SessionDep,
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.WORKFLOW_ESCALATE.value)),
) -> WorkflowDetail:
    service = _service(session, state)
    workflow = await service.escalate(
        workflow_id,
        decided_by=uuid.UUID(principal.user_id),
        reason=payload.reason,
        request_id=getattr(request.state, "request_id", None),
    )
    return WorkflowDetail.model_validate(workflow)
