"""End-to-end test harness.

Boots the real FastAPI application (running its lifespan: engine init, table
creation for SQLite, dev-admin seeding) against a temporary SQLite database and
drives it through an in-process httpx ASGI client. No network, no external
services — the LLM path resolves to the deterministic echo provider in local
mode, and storage/vector store are in-process.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def api_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    db_path = tmp_path / "e2e.db"
    os.environ.update(
        {
            "APP_ENV": "local",
            "APP_LOG_JSON": "false",
            "METRICS_ENABLED": "false",
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
            "STORAGE_USE_LOCAL_FS": "true",
            "LLM_ROUTER_POLICY": "prefer_online",
            "SEED_ADMIN_EMAIL": "admin@local.dev",
            "SEED_ADMIN_PASSWORD": "Admin123!Local",
        }
    )

    # Reset cached settings and any previously-initialised engine.
    from banking_ai.core.config import get_settings
    from banking_ai.db import session as session_module

    get_settings.cache_clear()
    session_module._engine = None
    session_module._sessionmaker = None

    from banking_ai.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    await session_module.dispose_engine()
    get_settings.cache_clear()


async def login_admin(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "Admin123!Local"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
