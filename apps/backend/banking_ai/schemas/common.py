"""Shared schema primitives: error envelope, pagination, base model."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for all API schemas (ORM-friendly, ignores unknown input)."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(ApiModel):
    """Canonical error envelope returned by every failing endpoint."""

    error: ErrorDetail


class PageMeta(ApiModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class Page(ApiModel, Generic[T]):
    """Generic paginated envelope."""

    items: list[T]
    meta: PageMeta

    @classmethod
    def build(cls, items: list[T], *, page: int, page_size: int, total: int) -> Page[T]:
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            meta=PageMeta(page=page, page_size=page_size, total=total, total_pages=total_pages),
        )


class PaginationParams(ApiModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
