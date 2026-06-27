"""Document service.

Coordinates the document-ingestion pipeline:

1. store the raw bytes in object storage (content-addressed key),
2. persist a ``documents`` metadata row,
3. chunk the extracted text,
4. embed each chunk with the configured embedder,
5. persist ``document_chunks`` + ``embeddings_metadata`` and index the vectors
   into the active vector store for retrieval.

Text extraction for binary formats (PDF/scan/OCR) is a documented integration
point; here we accept already-extracted UTF-8 text (or decode text uploads),
which keeps the pipeline deterministic and testable. Chunking is a simple,
deterministic word-window with overlap.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from banking_ai.ai.vector_store import Embedder, VectorRecord, VectorStore
from banking_ai.core.logging import get_logger
from banking_ai.db.models.document import Document, DocumentChunk, EmbeddingMetadata
from banking_ai.db.models.enums import DocumentStatus
from banking_ai.services.storage_service import ObjectStorage, content_key

logger = get_logger(__name__)


def chunk_text(text: str, *, size: int = 120, overlap: int = 20) -> list[str]:
    """Split text into overlapping word windows (deterministic)."""
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if window:
            chunks.append(" ".join(window))
        if start + size >= len(words):
            break
    return chunks


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: ObjectStorage,
        embedder: Embedder,
        vector_store: VectorStore,
    ) -> None:
        self._session = session
        self._storage = storage
        self._embedder = embedder
        self._vector_store = vector_store

    async def ingest(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        text: str | None = None,
        uploaded_by: uuid.UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Document:
        key = content_key(filename, data)
        await self._storage.put(key, data)

        document = Document(
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=key,
            sha256=key.split("/", 1)[0],
            status=DocumentStatus.PROCESSING,
            doc_metadata=metadata or {},
            uploaded_by=uploaded_by,
        )
        self._session.add(document)
        await self._session.flush()

        extracted = text if text is not None else _decode_text(data, content_type)
        chunks = chunk_text(extracted) if extracted else []

        records: list[VectorRecord] = []
        for index, chunk_content in enumerate(chunks):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk_content,
                token_count=max(1, len(chunk_content) // 4),
            )
            self._session.add(chunk)
            await self._session.flush()

            vector = self._embedder.embed(chunk_content)
            self._session.add(
                EmbeddingMetadata(
                    chunk_id=chunk.id,
                    model="hashing-embedder",
                    dimensions=self._embedder.dimensions,
                    vector=vector,
                )
            )
            records.append(
                VectorRecord(
                    chunk_id=str(chunk.id),
                    document_id=str(document.id),
                    text=chunk_content,
                    embedding=vector,
                    filename=document.filename,
                )
            )

        if records:
            await self._vector_store.upsert(records)

        document.status = DocumentStatus.PROCESSED if chunks else DocumentStatus.NEEDS_REVIEW
        await self._session.flush()
        logger.info(
            "document.ingested",
            document_id=str(document.id),
            chunks=len(chunks),
            status=document.status,
        )
        return document


def _decode_text(data: bytes, content_type: str) -> str:
    if content_type.startswith("text/") or content_type in (
        "application/json",
        "application/xml",
    ):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""
    # Binary formats (PDF, images) require an extraction/OCR step (documented).
    return ""
