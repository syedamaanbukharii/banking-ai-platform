"""Versioned API (v1) router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from banking_ai.api.v1 import admin, agents, audit, auth, documents, search, workflows

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(workflows.router)
api_router.include_router(agents.router)
api_router.include_router(search.router)
api_router.include_router(audit.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
