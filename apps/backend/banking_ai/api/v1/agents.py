"""Agent observability endpoints: inspect agent-run history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from banking_ai.api.deps import SessionDep, require_permissions
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal
from banking_ai.db.models.workflow import AgentRun
from banking_ai.schemas.common import Page
from banking_ai.schemas.workflow import AgentRunOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/{agent_name}/runs", response_model=Page[AgentRunOut])
async def list_agent_runs(
    agent_name: str,
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    workflow_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(require_permissions(Permission.AGENT_READ.value)),
) -> Page[AgentRunOut]:
    filters = [AgentRun.agent_name == agent_name]
    if workflow_id is not None:
        filters.append(AgentRun.workflow_id == workflow_id)

    total = await session.scalar(select(func.count()).select_from(AgentRun).where(*filters))
    rows = (
        (
            await session.execute(
                select(AgentRun)
                .where(*filters)
                .order_by(AgentRun.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [AgentRunOut.model_validate(r) for r in rows]
    return Page.build(items, page=page, page_size=page_size, total=int(total or 0))
