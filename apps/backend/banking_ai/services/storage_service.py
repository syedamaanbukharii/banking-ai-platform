"""Object storage service.

Documents are stored as opaque objects keyed by a content-addressed path; the
database holds only metadata and the storage key (never file bytes). For local
dev and tests this writes to a temp directory on the local filesystem
(``STORAGE_USE_LOCAL_FS=true``). In production the same interface is backed by
S3/MinIO (``boto3`` is an optional dependency, see ``[storage]`` extra); that
implementation is a documented seam and not on the default runtime path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from banking_ai.core.config import Settings
from banking_ai.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes) -> str: ...

    async def get(self, key: str) -> bytes: ...

    async def exists(self, key: str) -> bool: ...


def content_key(filename: str, data: bytes) -> str:
    """Content-addressed storage key: ``<sha256>/<filename>``."""
    digest = hashlib.sha256(data).hexdigest()
    safe_name = Path(filename).name or "file"
    return f"{digest}/{safe_name}"


class LocalFileStorage:
    """Filesystem-backed storage for local dev and tests."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        # Guard against path traversal in keys.
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError("Illegal storage key.")
        return path

    async def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("storage.put", key=key, bytes=len(data))
        return key

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Storage:
    """S3/MinIO-backed storage (documented production seam).

    Requires the optional ``[storage]`` extra (``boto3``). Not wired into the
    default runtime, which uses :class:`LocalFileStorage`. See docs/deployment.md.
    """

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        raise NotImplementedError(
            "S3Storage is a documented seam; set STORAGE_USE_LOCAL_FS=true for dev. "
            "Install the [storage] extra and implement with boto3 for production."
        )


def build_storage(settings: Settings, *, local_root: str | Path) -> ObjectStorage:
    if settings.storage_use_local_fs:
        return LocalFileStorage(local_root)
    return cast(ObjectStorage, S3Storage(settings))  # pragma: no cover
