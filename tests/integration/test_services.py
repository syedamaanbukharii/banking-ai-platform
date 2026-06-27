"""Integration tests for the service layer against a real (in-memory) database."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.unit.test_router import FakeProvider

from banking_ai.ai.router import ModelRouter
from banking_ai.ai.vector_store import HashingEmbedder, InMemoryVectorStore
from banking_ai.core.config import Settings
from banking_ai.core.errors import AuthenticationError, WorkflowStateError
from banking_ai.db.models.enums import WorkflowStatus, WorkflowType
from banking_ai.db.models.observability import ModelCall
from banking_ai.services.agent_executor import AgentExecutor
from banking_ai.services.audit_service import AuditService
from banking_ai.services.document_service import DocumentService
from banking_ai.services.observer import DbRouterObserver
from banking_ai.services.seed import seed_admin
from banking_ai.services.storage_service import LocalFileStorage
from banking_ai.services.user_service import UserService
from banking_ai.services.workflow_service import WorkflowService


@pytest.mark.asyncio
async def test_seed_admin_is_idempotent(session: AsyncSession) -> None:
    settings = Settings()
    admin1 = await seed_admin(session, settings)
    admin2 = await seed_admin(session, settings)
    assert admin1.id == admin2.id
    assert "system_admin" in admin1.role_names()
    # Admin can authenticate.
    svc = UserService(session, settings=settings)
    authed = await svc.authenticate(settings.seed_admin_email, settings.seed_admin_password)
    assert authed.id == admin1.id


@pytest.mark.asyncio
async def test_authenticate_rejects_bad_password(session: AsyncSession) -> None:
    settings = Settings()
    await seed_admin(session, settings)
    svc = UserService(session, settings=settings)
    with pytest.raises(AuthenticationError):
        await svc.authenticate(settings.seed_admin_email, "wrong-password")


@pytest.mark.asyncio
async def test_document_ingest_and_retrieve(session: AsyncSession, tmp_storage_root) -> None:
    embedder = HashingEmbedder(dimensions=128)
    store = InMemoryVectorStore()
    storage = LocalFileStorage(tmp_storage_root)
    svc = DocumentService(session, storage=storage, embedder=embedder, vector_store=store)
    text = "Wire transfers above ten thousand require enhanced due diligence review."
    doc = await svc.ingest(
        filename="policy.txt",
        content_type="text/plain",
        data=text.encode("utf-8"),
        text=text,
    )
    assert doc.status.value == "processed"
    assert await store.count() >= 1
    # Stored bytes are retrievable from object storage.
    assert await storage.exists(doc.storage_key)


@pytest.mark.asyncio
async def test_workflow_kyc_awaits_approval_then_approved(session: AsyncSession) -> None:
    admin = await seed_admin(session, Settings())
    executor = AgentExecutor()
    audit = AuditService(session)
    svc = WorkflowService(session, executor=executor, audit=audit)

    wf = await svc.start(
        workflow_type=WorkflowType.KYC,
        input_payload={
            "profile": {
                "full_name": "Jane Doe",
                "date_of_birth": "1990-01-02",
                "country": "US",
                "document_number": "X1",
            },
            "document_fields": {"full_name": "Jane Doe", "document_number": "X1"},
            "kind": "identity",
            "text": "Full Name: Jane Doe\nDocument Number: X1",
        },
        created_by=admin.id,
    )
    assert wf.status == WorkflowStatus.AWAITING_APPROVAL.value
    assert any(a.decision == "pending" for a in wf.approvals)

    approved = await svc.approve(wf.id, decided_by=admin.id, reason="looks good")
    assert approved.status == WorkflowStatus.COMPLETED.value
    assert all(a.decision != "pending" for a in approved.approvals)
    assert approved.approvals[0].decided_by == admin.id


@pytest.mark.asyncio
async def test_workflow_reject_path(session: AsyncSession) -> None:
    admin = await seed_admin(session, Settings())
    svc = WorkflowService(session, executor=AgentExecutor(), audit=AuditService(session))
    wf = await svc.start(
        workflow_type=WorkflowType.FRAUD_REVIEW,
        input_payload={
            "transaction": {
                "amount": 50000,
                "account_age_days": 2,
                "is_new_beneficiary": True,
                "beneficiary_country": "XX",
                "recent_failed_logins": 5,
            },
            "customer_avg_amount": 100,
        },
        created_by=admin.id,
    )
    assert wf.status == WorkflowStatus.AWAITING_APPROVAL.value
    rejected = await svc.reject(wf.id, decided_by=admin.id, reason="confirmed fraud")
    assert rejected.status == WorkflowStatus.REJECTED.value


@pytest.mark.asyncio
async def test_cannot_approve_completed_workflow(session: AsyncSession) -> None:
    admin = await seed_admin(session, Settings())
    # Compliance is not approval-gated -> completes immediately.
    embedder = HashingEmbedder(dimensions=64)
    store = InMemoryVectorStore()
    svc2 = WorkflowService(
        session,
        executor=AgentExecutor(embedder=embedder, vector_store=store),
        audit=AuditService(session),
    )
    wf = await svc2.start(
        workflow_type=WorkflowType.COMPLIANCE,
        input_payload={"question": "anything", "query": "anything"},
        created_by=admin.id,
    )
    assert wf.status == WorkflowStatus.COMPLETED.value
    with pytest.raises(WorkflowStateError):
        await svc2.approve(wf.id, decided_by=admin.id)


@pytest.mark.asyncio
async def test_review_queue_lists_awaiting(session: AsyncSession) -> None:
    admin = await seed_admin(session, Settings())
    svc = WorkflowService(session, executor=AgentExecutor(), audit=AuditService(session))
    await svc.start(
        workflow_type=WorkflowType.FRAUD_REVIEW,
        input_payload={"transaction": {"amount": 99999, "beneficiary_country": "XX"}},
        created_by=admin.id,
    )
    rows, total = await svc.review_queue()
    assert total >= 1
    assert all(
        r.status in (WorkflowStatus.AWAITING_APPROVAL.value, WorkflowStatus.ESCALATED.value)
        for r in rows
    )


@pytest.mark.asyncio
async def test_db_router_observer_persists_model_calls(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    observer = DbRouterObserver(sessionmaker_fixture)
    router = ModelRouter(
        providers=[FakeProvider("groq", fail=True), FakeProvider("local_gemma")],
        policy="prefer_online",
        observer=observer,
    )
    from banking_ai.ai.types import ChatMessage, CompletionRequest, Role

    await router.complete(CompletionRequest(messages=[ChatMessage(role=Role.USER, content="hi")]))
    async with sessionmaker_fixture() as s:
        count = await s.scalar(select(func.count()).select_from(ModelCall))
    # One failure (groq) + one success (local_gemma) persisted.
    assert count == 2


@pytest.mark.asyncio
async def test_workflow_failure_marks_failed(session: AsyncSession) -> None:
    admin = await seed_admin(session, Settings())
    # Compliance workflow without embedder/store -> retrieval agent step fails.
    svc = WorkflowService(session, executor=AgentExecutor(), audit=AuditService(session))
    wf = await svc.start(
        workflow_type=WorkflowType.COMPLIANCE,
        input_payload={"question": "x"},
        created_by=admin.id,
    )
    assert wf.status == WorkflowStatus.FAILED.value
    assert wf.error is not None
