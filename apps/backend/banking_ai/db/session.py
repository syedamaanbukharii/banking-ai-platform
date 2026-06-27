"""Async database engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from banking_ai.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url
    # SQLite (used by tests) does not accept pool sizing kwargs.
    if url.startswith("sqlite"):
        return create_async_engine(url, echo=settings.database_echo, future=True)
    return create_async_engine(
        url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    """Initialise (or return) the process-wide async engine and sessionmaker."""
    global _engine, _sessionmaker
    settings = settings or get_settings()
    if _engine is None:
        _engine = _build_engine(settings)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None  # nosec B101 - invariant after init_engine
    return _sessionmaker


async def dispose_engine() -> None:
    """Dispose of the engine on shutdown (graceful)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session.

    Commits on success, rolls back on exception, always closes.
    """
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
