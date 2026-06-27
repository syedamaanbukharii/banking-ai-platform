"""Audit log endpoints (read-only; the log is append-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from banking_ai.api.deps import SessionDep, require_permissions
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal
from banking_ai.db.models.observability import AuditLog
from banking_ai.schemas.audit import AuditLogOut
from banking_ai.schemas.common import Page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=Page[AuditLogOut])
async def list_audit_logs(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    principal: Principal = Depends(require_permissions(Permission.AUDIT_READ.value)),
) -> Page[AuditLogOut]:
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)

    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*filters))
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [AuditLogOut.model_validate(r) for r in rows]
    return Page.build(items, page=page, page_size=page_size, total=int(total or 0))
