"""FastAPI application factory and entrypoint.

Wires together configuration, logging, middleware, exception handlers, the
versioned API router, Prometheus metrics, and lifespan startup/shutdown
(engine init, optional dev seeding, graceful disposal).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from banking_ai.api.exception_handlers import register_exception_handlers
from banking_ai.api.middleware import RequestContextMiddleware
from banking_ai.api.state import build_app_state
from banking_ai.api.v1 import api_router
from banking_ai.core.config import AppEnv, Settings, get_settings
from banking_ai.core.logging import configure_logging, get_logger
from banking_ai.db.session import dispose_engine, get_sessionmaker

logger = get_logger(__name__)

API_PREFIX = "/api/v1"


async def _seed_if_local(settings: Settings) -> None:
    """Seed RBAC + a dev admin on startup in local environments only."""
    if settings.app_env is not AppEnv.LOCAL:
        return
    from banking_ai.db.models import Base
    from banking_ai.db.session import init_engine
    from banking_ai.services.seed import seed_admin

    engine = init_engine(settings)
    # Create tables for SQLite dev runs (production uses Alembic migrations).
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with get_sessionmaker()() as session:
        await seed_admin(session, settings)
        await session.commit()
    logger.info("startup.seeded", env=settings.app_env.value)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.app_log_level, json_logs=settings.app_log_json)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.app_state = build_app_state(settings)
        with contextlib.suppress(Exception):
            await _seed_if_local(settings)
        logger.info("startup.complete", env=settings.app_env.value)
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                await app.state.app_state.router.aclose()
            await dispose_engine()
            logger.info("shutdown.complete")

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Enterprise Agentic AI Platform for Banking Operations.",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)

    if settings.metrics_enabled:
        _mount_metrics(app)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "version": "1.0.0", "docs": "/docs"}

    return app


def _mount_metrics(app: FastAPI) -> None:
    """Mount a Prometheus metrics endpoint if the client library is available."""
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except Exception:  # pragma: no cover - metrics optional
        logger.warning("metrics.unavailable")
        return

    from fastapi import Response

    @app.get("/metrics", tags=["meta"])
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app = create_app()


def run() -> None:  # pragma: no cover - convenience entrypoint
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "banking_ai.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
