"""End-to-end API tests exercising the full request path."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.e2e.conftest import auth_header, login_admin


@pytest.mark.asyncio
async def test_health_and_ready(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/v1/health")).json() == {"status": "ok"}
    assert (await api_client.get("/api/v1/ready")).json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_login_and_me(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    resp = await api_client.get("/api/v1/auth/me", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@local.dev"
    assert "system_admin" in body["roles"]
    assert "workflow:approve" in body["permissions"]


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_error"


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/workflows")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_error"


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(api_client: AsyncClient) -> None:
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "Admin123!Local"},
    )
    refresh_token = login.json()["refresh_token"]
    resp = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_document_upload_then_search(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    content = (
        b"Wire transfers above ten thousand dollars require enhanced due "
        b"diligence and a senior compliance sign-off."
    )
    up = await api_client.post(
        "/api/v1/documents/upload",
        headers=auth_header(token),
        files={"file": ("policy.txt", content, "text/plain")},
        data={"kind": "generic"},
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["status"] == "processed"

    # The uploaded chunks are now searchable.
    search = await api_client.get(
        "/api/v1/search",
        headers=auth_header(token),
        params={"q": "enhanced due diligence wire transfer", "top_k": 3},
    )
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits
    assert "due diligence" in hits[0]["text"]


@pytest.mark.asyncio
async def test_kyc_workflow_full_hitl_approval(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    start = await api_client.post(
        "/api/v1/workflows/start",
        headers=auth_header(token),
        json={
            "workflow_type": "kyc",
            "input_payload": {
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
        },
    )
    assert start.status_code == 201, start.text
    wf = start.json()
    assert wf["status"] == "awaiting_approval"
    workflow_id = wf["id"]

    # It appears in the review queue.
    queue = await api_client.get("/api/v1/workflows", headers=auth_header(token))
    assert any(item["id"] == workflow_id for item in queue.json()["items"])

    # Approve it -> completed.
    approve = await api_client.post(
        f"/api/v1/workflows/{workflow_id}/approve",
        headers=auth_header(token),
        json={"reason": "verified"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "completed"

    # Agent runs are observable.
    runs = await api_client.get("/api/v1/agents/kyc_agent/runs", headers=auth_header(token))
    assert runs.status_code == 200
    assert runs.json()["meta"]["total"] >= 1


@pytest.mark.asyncio
async def test_fraud_workflow_reject_flow(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    start = await api_client.post(
        "/api/v1/workflows/start",
        headers=auth_header(token),
        json={
            "workflow_type": "fraud_review",
            "input_payload": {
                "transaction": {
                    "amount": 50000,
                    "account_age_days": 2,
                    "is_new_beneficiary": True,
                    "beneficiary_country": "XX",
                    "recent_failed_logins": 5,
                },
                "customer_avg_amount": 100,
            },
        },
    )
    assert start.status_code == 201, start.text
    workflow_id = start.json()["id"]
    assert start.json()["status"] == "awaiting_approval"

    reject = await api_client.post(
        f"/api/v1/workflows/{workflow_id}/reject",
        headers=auth_header(token),
        json={"reason": "confirmed fraudulent"},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_approving_non_pending_workflow_errors(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    # Compliance workflow is not approval-gated -> completes immediately.
    start = await api_client.post(
        "/api/v1/workflows/start",
        headers=auth_header(token),
        json={
            "workflow_type": "compliance",
            "input_payload": {"question": "What are wire transfer rules?"},
        },
    )
    assert start.status_code == 201, start.text
    workflow_id = start.json()["id"]
    assert start.json()["status"] == "completed"

    bad = await api_client.post(
        f"/api/v1/workflows/{workflow_id}/approve",
        headers=auth_header(token),
        json={"reason": "n/a"},
    )
    assert bad.status_code == 409
    assert bad.json()["error"]["code"] == "invalid_workflow_state"


@pytest.mark.asyncio
async def test_audit_log_records_actions(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    await api_client.post(
        "/api/v1/workflows/start",
        headers=auth_header(token),
        json={
            "workflow_type": "fraud_review",
            "input_payload": {"transaction": {"amount": 99999, "beneficiary_country": "XX"}},
        },
    )
    logs = await api_client.get(
        "/api/v1/audit/logs",
        headers=auth_header(token),
        params={"resource_type": "workflow"},
    )
    assert logs.status_code == 200
    assert logs.json()["meta"]["total"] >= 1


@pytest.mark.asyncio
async def test_router_config_exposed_to_admin(api_client: AsyncClient) -> None:
    token = await login_admin(api_client)
    resp = await api_client.get("/api/v1/admin/router", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy"] == "prefer_online"
    # Local env appends the echo provider as a last-resort.
    assert "echo" in body["providers"]
