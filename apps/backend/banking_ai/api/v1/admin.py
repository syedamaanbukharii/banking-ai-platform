"""Operational endpoints: health, readiness, and router configuration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from banking_ai.api.deps import SessionDep, StateDep, require_permissions
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal

router = APIRouter(tags=["admin"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — process is up (no dependencies checked)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: SessionDep) -> dict[str, str]:
    """Readiness probe — verifies the database is reachable."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/admin/router")
async def router_config(
    state: StateDep,
    principal: Principal = Depends(require_permissions(Permission.ADMIN_READ.value)),
) -> dict[str, Any]:
    """Expose the active model-routing policy and provider chain (auditable)."""
    return {
        "policy": state.router.policy,
        "providers": state.router.provider_names,
    }
