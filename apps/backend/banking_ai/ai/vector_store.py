"""Vector store and embedding abstractions.

The platform needs semantic retrieval (RAG) for the compliance/knowledge agents.
To keep the repository runnable and its tests deterministic without a native
``pgvector`` build or a downloaded embedding model, this module provides:

* :class:`Embedder` — a tiny protocol for turning text into vectors.
* :class:`HashingEmbedder` — a deterministic, dependency-free embedder (a hashed
  bag-of-words projected onto a fixed dimensionality, L2-normalised). It is NOT
  a semantic model; it exists so retrieval is reproducible offline. Production
  swaps in a real sentence-embedding model behind the same protocol.
* :class:`InMemoryVectorStore` — cosine-similarity search over an in-process
  index (used by dev and tests).
* :class:`PgVectorStore` — a documented production seam (see ``docs/architecture.md``)
  that stores embeddings in PostgreSQL/pgvector. It is intentionally not wired
  into the default runtime path.

The store interface is stable, so moving from in-memory to pgvector is a
configuration change, not an agent change.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    @property
    def dimensions(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Deterministic hashed bag-of-words embedder (offline, reproducible)."""

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        return _l2_normalise(vec)


def _l2_normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    # Vectors are L2-normalised, so the dot product is the cosine similarity.
    return sum(x * y for x, y in zip(a, b, strict=False))


@dataclass
class VectorRecord:
    chunk_id: str
    document_id: str
    text: str
    embedding: list[float]
    filename: str | None = None


@dataclass
class ScoredRecord:
    record: VectorRecord
    score: float


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord]) -> None: ...

    async def query(self, embedding: list[float], *, top_k: int = 5) -> list[ScoredRecord]: ...

    async def count(self) -> int: ...


@dataclass
class InMemoryVectorStore:
    """Cosine-similarity search over an in-process list (dev/test backend)."""

    _records: dict[str, VectorRecord] = field(default_factory=dict)

    async def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[record.chunk_id] = record

    async def query(self, embedding: list[float], *, top_k: int = 5) -> list[ScoredRecord]:
        scored = [
            ScoredRecord(record=r, score=cosine_similarity(embedding, r.embedding))
            for r in self._records.values()
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: max(0, top_k)]

    async def count(self) -> int:
        return len(self._records)


class PgVectorStore:
    """Production vector store backed by PostgreSQL + pgvector.

    Documented seam only: the default runtime uses :class:`InMemoryVectorStore`
    so the stack runs and tests pass without a native pgvector extension. A
    production deployment sets ``VECTOR_BACKEND=pgvector`` and provides a
    Postgres instance with the extension enabled; the implementation would issue
    ``<=>`` (cosine distance) queries against the ``embeddings_metadata`` table's
    vector column. See docs/architecture.md ("Vector store") for the rationale.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        raise NotImplementedError(
            "PgVectorStore is a documented production seam; set VECTOR_BACKEND=memory "
            "for local/dev runs. See docs/architecture.md."
        )
