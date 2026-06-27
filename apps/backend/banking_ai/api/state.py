"""Application state.

Process-wide singletons that are expensive or stateful and should be shared
across requests: the model router (with its DB-backed observer), the embedder,
the in-process vector store, and object storage. These are attached to
``app.state`` in the lifespan handler and read via dependencies.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from banking_ai.ai.factory import build_router
from banking_ai.ai.router import ModelRouter
from banking_ai.ai.vector_store import Embedder, HashingEmbedder, InMemoryVectorStore, VectorStore
from banking_ai.core.config import Settings
from banking_ai.db.session import get_sessionmaker, init_engine
from banking_ai.services.observer import DbRouterObserver
from banking_ai.services.storage_service import LocalFileStorage, ObjectStorage, build_storage


@dataclass
class AppState:
    settings: Settings
    router: ModelRouter
    embedder: Embedder
    vector_store: VectorStore
    storage: ObjectStorage


def build_app_state(settings: Settings) -> AppState:
    """Construct shared services from settings (idempotent per process)."""
    init_engine(settings)
    observer = DbRouterObserver(get_sessionmaker())
    router = build_router(settings, observer=observer)
    embedder = HashingEmbedder(dimensions=settings.vector_dimensions)
    vector_store = InMemoryVectorStore()

    if settings.storage_use_local_fs:
        root = Path(tempfile.gettempdir()) / "banking-ai-objects"
        storage: ObjectStorage = LocalFileStorage(root)
    else:  # pragma: no cover - production seam
        storage = build_storage(settings, local_root=Path(tempfile.gettempdir()))

    return AppState(
        settings=settings,
        router=router,
        embedder=embedder,
        vector_store=vector_store,
        storage=storage,
    )
