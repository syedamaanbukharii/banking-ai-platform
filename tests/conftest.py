"""Shared pytest fixtures.

Provides an isolated in-memory SQLite database per test (async), with all tables
created from the ORM metadata. No external services are required: the LLM is
mocked/echoed, storage is a temp dir, and the vector store is in-memory.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from banking_ai.db.models import Base


@pytest_asyncio.fixture
async def sessionmaker_fixture() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield maker
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker_fixture() as s:
        yield s
        await s.commit()


@pytest.fixture
def tmp_storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "objects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
