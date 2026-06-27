"""Document, chunk and embedding-metadata models.

Per the data design rules, file *contents* are not stored in the database. The
``documents`` row holds metadata plus a ``storage_key`` pointing at object
storage (MinIO/S3). Chunk text is stored for retrieval; the embedding vector is
stored as JSON in the portable backend and mirrored to pgvector in production.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from banking_ai.db.base import Base, TimestampMixin, UUIDMixin
from banking_ai.db.models.enums import DocumentStatus


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Object-storage key (file bytes live in MinIO/S3, never in the DB).
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.UPLOADED, nullable=False)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
    embedding: Mapped[EmbeddingMetadata | None] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", uselist=False
    )


class EmbeddingMetadata(UUIDMixin, TimestampMixin, Base):
    """Embedding provenance + vector.

    The ``vector`` column is JSON for portability. In production the pgvector
    adapter maintains a parallel ``vector(dim)`` column for ANN search; this row
    remains the system-of-record for provenance (model, dimensions).
    """

    __tablename__ = "embeddings_metadata"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)

    chunk: Mapped[DocumentChunk] = relationship(back_populates="embedding")


__all__ = ["Document", "DocumentChunk", "EmbeddingMetadata"]
