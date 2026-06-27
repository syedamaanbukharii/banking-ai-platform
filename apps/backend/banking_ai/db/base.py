"""SQLAlchemy declarative base and common column mixins.

Design choices for portability (tests run on SQLite, prod on PostgreSQL):
* ``Uuid`` primary keys map to native ``uuid`` on PostgreSQL and ``CHAR(32)`` on
  SQLite, so the same models work in both.
* JSON columns use the dialect-agnostic ``JSON`` type. Production migrations can
  upgrade these to ``JSONB`` on PostgreSQL (documented in docs/architecture.md).
* Timestamps default in Python for deterministic, dialect-independent behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
