"""Document endpoints: upload (ingest + index) and metadata read."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select

from banking_ai.api.deps import SessionDep, StateDep, require_permissions
from banking_ai.core.errors import NotFoundError
from banking_ai.core.rbac import Permission
from banking_ai.core.security import Principal
from banking_ai.db.models.document import Document
from banking_ai.schemas.common import ErrorResponse
from banking_ai.schemas.document import DocumentOut
from banking_ai.services.audit_service import AuditService
from banking_ai.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

_UPLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
}
_GET_RESPONSES: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}

_MAX_BYTES = 25 * 1024 * 1024  # 25 MiB upload ceiling


@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=201,
    responses=_UPLOAD_RESPONSES,
)
async def upload_document(
    request: Request,
    session: SessionDep,
    state: StateDep,
    file: UploadFile = File(...),
    kind: str = Form("generic"),
    principal: Principal = Depends(require_permissions(Permission.DOCUMENT_UPLOAD.value)),
) -> DocumentOut:
    data = await file.read()
    if len(data) > _MAX_BYTES:
        from banking_ai.core.errors import ValidationAppError

        raise ValidationAppError(
            "Uploaded file exceeds the size limit.",
            details={"max_bytes": _MAX_BYTES, "size": len(data)},
        )

    service = DocumentService(
        session,
        storage=state.storage,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )
    document = await service.ingest(
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        uploaded_by=uuid.UUID(principal.user_id),
        metadata={"kind": kind},
    )
    await AuditService(session).record(
        action="document.uploaded",
        resource_type="document",
        resource_id=str(document.id),
        actor_id=uuid.UUID(principal.user_id),
        actor_email=principal.email,
        request_id=getattr(request.state, "request_id", None),
        context={"filename": document.filename, "size": document.size_bytes},
    )
    return DocumentOut.model_validate(document)


@router.get("/{document_id}", response_model=DocumentOut, responses=_GET_RESPONSES)
async def get_document(
    document_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require_permissions(Permission.DOCUMENT_READ.value)),
) -> DocumentOut:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return DocumentOut.model_validate(document)
