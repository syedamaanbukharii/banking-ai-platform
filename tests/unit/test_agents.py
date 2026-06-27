"""Unit tests for agents (deterministic logic, mocked LLM)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from banking_ai.agents.compliance import ComplianceAgent, ComplianceInput
from banking_ai.agents.document import DocumentAgent, DocumentAgentInput, parse_fields
from banking_ai.agents.fraud import FraudAgent, FraudInput, Transaction
from banking_ai.agents.kyc import KycAgent, KycInput
from banking_ai.agents.loan import LoanAgent, LoanInput
from banking_ai.agents.orchestrator import OrchestratorAgent, OrchestratorInput
from banking_ai.agents.retrieval import RetrievalAgent, RetrievalInput
from banking_ai.agents.summarization import SummarizationAgent, SummarizationInput
from banking_ai.ai.router import ModelRouter
from banking_ai.ai.vector_store import (
    HashingEmbedder,
    InMemoryVectorStore,
    VectorRecord,
)
from banking_ai.db.models.enums import RiskLevel, WorkflowType
from tests.unit.test_router import FakeProvider

# --- document agent ---


def test_parse_fields_basic() -> None:
    text = "Full Name: Jane Doe\nDate of Birth = 1990-01-02\njunk line\nCountry: US"
    parsed = parse_fields(text)
    assert parsed["full_name"] == "Jane Doe"
    assert parsed["date_of_birth"] == "1990-01-02"
    assert parsed["country"] == "US"


@pytest.mark.asyncio
async def test_document_agent_flags_missing_fields() -> None:
    agent = DocumentAgent()
    doc_id = uuid.uuid4()
    payload = DocumentAgentInput(
        document_id=doc_id,
        kind="identity",
        text="Full Name: Jane Doe\nDocument Number: X123",
    )
    outcome = await agent.execute(payload)
    assert outcome.status == "succeeded"
    review = outcome.output
    assert review is not None
    assert "date_of_birth" in review.missing_fields
    assert "expiry_date" in review.missing_fields
    assert review.requires_human_review is True


@pytest.mark.asyncio
async def test_document_agent_complete_identity() -> None:
    agent = DocumentAgent()
    text = (
        "Full Name: Jane Doe\nDate Of Birth: 1990-01-02\n"
        "Document Number: X123\nExpiry Date: 2030-01-01"
    )
    outcome = await agent.execute(
        DocumentAgentInput(document_id=uuid.uuid4(), kind="identity", text=text)
    )
    assert outcome.output is not None
    assert outcome.output.missing_fields == []
    assert outcome.output.requires_human_review is False


# --- kyc agent ---


@pytest.mark.asyncio
async def test_kyc_name_mismatch_triggers_review() -> None:
    agent = KycAgent()
    payload = KycInput(
        profile={
            "full_name": "Jane Doe",
            "date_of_birth": "1990-01-02",
            "country": "US",
            "document_number": "X1",
        },
        document_fields={"full_name": "John Smith", "document_number": "X1"},
        today=date(2024, 1, 1),
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.requires_human_review is True
    assert any("does not match" in i for i in result.inconsistencies)
    assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)


@pytest.mark.asyncio
async def test_kyc_minor_is_high_risk() -> None:
    agent = KycAgent()
    payload = KycInput(
        profile={
            "full_name": "Kid A",
            "date_of_birth": "2010-01-01",
            "country": "US",
            "document_number": "X1",
        },
        today=date(2024, 1, 1),
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.risk_level == RiskLevel.HIGH
    assert result.requires_human_review is True


@pytest.mark.asyncio
async def test_kyc_clean_profile_passes() -> None:
    agent = KycAgent()
    payload = KycInput(
        profile={
            "full_name": "Jane Doe",
            "date_of_birth": "1990-01-02",
            "country": "US",
            "document_number": "X1",
        },
        document_fields={"full_name": "JANE  DOE", "document_number": "X1"},
        today=date(2024, 1, 1),
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.complete is True
    assert result.inconsistencies == []
    assert result.requires_human_review is False
    assert result.risk_level == RiskLevel.LOW


# --- fraud agent ---


@pytest.mark.asyncio
async def test_fraud_low_risk_small_transaction() -> None:
    agent = FraudAgent()
    payload = FraudInput(
        transaction=Transaction(amount=20.0, account_age_days=900),
        customer_avg_amount=50.0,
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.score == 0
    assert result.risk_level == RiskLevel.LOW
    assert result.requires_human_review is False


@pytest.mark.asyncio
async def test_fraud_high_risk_combines_signals() -> None:
    agent = FraudAgent()
    payload = FraudInput(
        transaction=Transaction(
            amount=25_000.0,
            account_age_days=5,
            is_new_beneficiary=True,
            beneficiary_country="XX",
            recent_failed_logins=4,
            hour_of_day=3,
        ),
        customer_avg_amount=100.0,
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.score >= 70
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.requires_human_review is True
    rules = {s.rule for s in result.signals}
    assert "large_absolute_amount" in rules
    assert "high_risk_destination" in rules


# --- loan agent ---


@pytest.mark.asyncio
async def test_loan_affordable_is_low_risk() -> None:
    agent = LoanAgent()
    payload = LoanInput(
        monthly_income=8000,
        monthly_debt=200,
        monthly_expenses=2000,
        loan_amount=10_000,
        term_months=36,
        annual_interest_rate=0.06,
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.risk_level == RiskLevel.LOW
    assert result.requires_human_review is True  # always needs sign-off


@pytest.mark.asyncio
async def test_loan_unaffordable_is_high_risk() -> None:
    agent = LoanAgent()
    payload = LoanInput(
        monthly_income=2000,
        monthly_debt=800,
        monthly_expenses=1000,
        loan_amount=50_000,
        term_months=24,
        annual_interest_rate=0.12,
    )
    result = (await agent.execute(payload)).output
    assert result is not None
    assert result.risk_level == RiskLevel.HIGH


def test_loan_zero_interest_payment() -> None:
    from banking_ai.agents.loan import _monthly_payment

    payment = _monthly_payment(principal=1200, annual_rate=0.0, term_months=12)
    assert payment == pytest.approx(100.0)


# --- retrieval + compliance agents ---


async def _seed_store() -> tuple[HashingEmbedder, InMemoryVectorStore]:
    embedder = HashingEmbedder(dimensions=128)
    store = InMemoryVectorStore()
    docs = {
        "wire transfers above 10000 require enhanced due diligence": "wire policy",
        "customer identification requires a government issued id": "kyc policy",
        "cooling off period for new accounts is five business days": "account policy",
    }
    records = []
    for text, fname in docs.items():
        records.append(
            VectorRecord(
                chunk_id=str(uuid.uuid4()),
                document_id=str(uuid.uuid4()),
                text=text,
                embedding=embedder.embed(text),
                filename=fname,
            )
        )
    await store.upsert(records)
    return embedder, store


@pytest.mark.asyncio
async def test_retrieval_ranks_relevant_chunk_first() -> None:
    embedder, store = await _seed_store()
    agent = RetrievalAgent(embedder=embedder, store=store)
    out = (await agent.execute(RetrievalInput(query="wire transfer due diligence", top_k=3))).output
    assert out is not None
    assert out.hits
    assert "wire transfers" in out.hits[0].text


@pytest.mark.asyncio
async def test_compliance_extractive_without_router() -> None:
    embedder, store = await _seed_store()
    agent = ComplianceAgent(embedder=embedder, store=store, router=None)
    out = (
        await agent.execute(
            ComplianceInput(question="What is required for large wire transfers?", top_k=2)
        )
    ).output
    assert out is not None
    assert out.grounded is True
    assert len(out.citations) == 2
    assert out.citations[0].marker == 1


@pytest.mark.asyncio
async def test_compliance_with_router_synthesis() -> None:
    embedder, store = await _seed_store()
    router = ModelRouter(
        providers=[FakeProvider("groq", text="Grounded answer [1].")],
        policy="online_only",
    )
    agent = ComplianceAgent(embedder=embedder, store=store, router=router)
    out = (await agent.execute(ComplianceInput(question="wire transfer rules", top_k=2))).output
    assert out is not None
    assert out.answer == "Grounded answer [1]."
    assert out.model_used is not None


@pytest.mark.asyncio
async def test_compliance_no_results_not_grounded() -> None:
    embedder = HashingEmbedder(dimensions=64)
    store = InMemoryVectorStore()
    agent = ComplianceAgent(embedder=embedder, store=store)
    out = (await agent.execute(ComplianceInput(question="anything"))).output
    assert out is not None
    assert out.grounded is False
    assert out.citations == []


# --- summarization agent (LLM via fake provider) ---


@pytest.mark.asyncio
async def test_summarization_uses_router() -> None:
    router = ModelRouter(
        providers=[FakeProvider("groq", text="A short summary.")], policy="online_only"
    )
    agent = SummarizationAgent(router=router)
    out = (await agent.execute(SummarizationInput(content="long text here"))).output
    assert out is not None
    assert out.summary == "A short summary."
    assert out.used_fallback is False
    assert out.model_used.startswith("groq:")


@pytest.mark.asyncio
async def test_summarization_without_router_fails_gracefully() -> None:
    agent = SummarizationAgent(router=None)
    outcome = await agent.execute(SummarizationInput(content="x"))
    # BaseAgent converts the AgentError into a failed outcome rather than raising.
    assert outcome.status == "failed"
    assert outcome.output is None
    assert outcome.error is not None


# --- orchestrator ---


@pytest.mark.asyncio
async def test_orchestrator_kyc_plan_is_approval_gated() -> None:
    agent = OrchestratorAgent()
    plan = (await agent.execute(OrchestratorInput(workflow_type=WorkflowType.KYC))).output
    assert plan is not None
    assert plan.requires_human_approval is True
    assert plan.approval_permission == "kyc:review"
    assert [s.agent for s in plan.steps] == ["document_agent", "kyc_agent"]


@pytest.mark.asyncio
async def test_orchestrator_compliance_plan_not_gated() -> None:
    agent = OrchestratorAgent()
    plan = (await agent.execute(OrchestratorInput(workflow_type=WorkflowType.COMPLIANCE))).output
    assert plan is not None
    assert plan.requires_human_approval is False
    assert plan.approval_permission is None
