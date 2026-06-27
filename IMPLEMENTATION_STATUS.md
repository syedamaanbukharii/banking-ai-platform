# Implementation Status

An honest, section-by-section map of the specification to what this repository
actually contains. Status values:

- **Implemented** — built and exercised by the automated test suite.
- **Scaffolded** — real, coherent starting code/config that is intentionally not a
  turnkey production deployment.
- **Documented seam** — a stable interface with a portable default, and the production
  implementation described but not wired into the default runtime (so the repo runs and
  tests pass offline).

Every deviation is justified. The guiding constraint: the platform must run end to end
and pass a green quality gate **without any external services or secrets**, while the
path to production is a configuration change rather than a rewrite.

## Quality gate (current)

`ruff` ✓ · `black --check` ✓ · `mypy` (strict, 70 files) ✓ · `bandit` ✓ (0 issues) ·
`pytest` ✓ **53 passed** · coverage **~90%** (gate 70%) · Alembic upgrade/downgrade ✓.

## Architecture layers

| Spec layer | Status | Where |
| --- | --- | --- |
| API / interface | Implemented | `api/` (FastAPI app, v1 routers, deps, middleware, error handlers) |
| Orchestration | Implemented (in-process) · Temporal **documented seam** | `agents/orchestrator.py`, `services/workflow_service.py`, `apps/worker/` |
| Agents | Implemented | `agents/` |
| Model routing | Implemented | `ai/router.py`, `ai/factory.py`, `ai/providers/` |
| Knowledge / retrieval (RAG) | Implemented (in-memory) · pgvector **documented seam** | `ai/vector_store.py`, `agents/retrieval.py`, `agents/compliance.py` |
| Data / persistence | Implemented | `db/` (18 tables), `migrations/` |
| Identity / RBAC | Implemented (local JWT) · OIDC **documented seam** | `core/security.py`, `core/rbac.py`, `services/user_service.py` |
| Observability / governance | Implemented (audit, model_calls, cost, metrics) | `services/audit_service.py`, `services/observer.py`, `core/logging.py`, `/metrics` |
| Storage | Implemented (local FS) · S3/MinIO **documented seam** | `services/storage_service.py` |

## Agents

All ten agents from the spec are **Implemented** with typed I/O and unit tests:
orchestrator, document, kyc, fraud, compliance, retrieval, summarization, loan,
notification, audit. Decision-path logic (KYC, fraud, loan, document validation) is
deterministic and explainable; summarization and compliance use the model router and
are mockable.

## Model router

**Implemented.** Ordered provider chain with policies (`prefer_online` /
`online_only` / `offline_only`); Groq (online primary) and local-Gemma (offline
fallback) as OpenAI-compatible providers; offline-aware availability; failover on
`LLMProviderError`; one `model_calls` record per attempt (failures included);
DB-backed observer persisting `model_calls` + `cost_tracking`; never silently switches
(fallback reason recorded; `/admin/router` exposes the live chain).

- **Deviation — `echo` provider added.** A deterministic, no-network, no-key stub,
  appended **only in local env** as a last resort so the platform runs with zero
  credentials. Never added outside local, so production cannot silently serve a
  non-model response. Justification: runnability without secrets.
- **Deviation — providers are mocked in tests.** No real Groq/Gemma calls in CI (no
  secrets, deterministic). Real HTTP client code is implemented and used at runtime.

## Human-in-the-loop

**Implemented.** Guarded workflow state machine (`running → awaiting_approval →
approved/rejected/escalated → completed`), pending `approvals` rows with the required
permission, a manual-review queue, invalid-transition guard (409
`invalid_workflow_state`), and audited decisions. Covered by integration and e2e tests
(KYC approve flow, fraud reject flow).

## Data model

**Implemented — 18 tables** (the spec's 16 entities plus the two normalised
association tables `user_roles`, `role_permissions`): users, roles, permissions,
applications, workflows, agent_runs, approvals, task_status, documents,
document_chunks, embeddings_metadata, audit_logs, model_calls, cost_tracking, feedback,
incidents.

- **Deviation — embedding vector stored as JSON.** Portable across SQLite/Postgres; a
  pgvector column is the production mirror (documented). `embeddings_metadata` remains
  the provenance system-of-record.
- **Deviation — file bytes not in the DB.** `documents.storage_key` points at object
  storage, per data-design best practice.

## API

**Implemented.** Versioned under `/api/v1`: auth (login/refresh/me), documents
(upload/get), workflows (start/get/approve/reject/escalate/queue), agents (runs),
search, audit (logs), admin (router), plus health/ready/metrics. Consistent error
envelope, pagination, request-id propagation, OpenAPI at `/docs`.

## Tests

**Implemented.** Unit (router + agents), integration (services + real in-memory DB),
e2e (full API over in-process ASGI). Deterministic and offline; LLM mocked; 53 tests,
~90% coverage.

## CI/CD

**Implemented (CI)** — `.github/workflows/ci.yml`: ruff, black, mypy, bandit,
pytest+coverage, Alembic upgrade/downgrade, backend image build, frontend build.
**Scaffolded (release)** — `.github/workflows/release.yml`: build/push images to GHCR
on tag, deploy to `staging`, then `production` behind a GitHub Environment approval
gate. The actual `kubectl`/`helm` deploy step is a documented placeholder (no live
cluster).

## Local stack (Docker Compose)

**Implemented/Scaffolded** — `docker-compose.yml` brings up backend + worker +
Postgres + Redis + MinIO + Keycloak + Prometheus + Grafana, with config files for
Prometheus, Grafana (datasource + dashboard), and a Keycloak realm export. The backend
image build, healthcheck, migrations-on-start, and Prometheus scrape are real; the full
stack is meant for local/demo use, not hardened production.

## Documentation

**Implemented** — `README.md` plus `docs/`: architecture, api, agents, auth,
deployment, testing, security, contributing. Plus this status document.

## Frontend

**Scaffolded** — `apps/frontend/` is a Next.js + TypeScript + Tailwind project with an
API client and a functional HITL operator console (login → review queue →
approve/reject) and a Dockerfile. Full operator UX (document upload, search, audit
views, dashboards) is intentionally out of scope for this pass; the backend is the
focus. `npm install`/build are not run in this environment but the project is coherent
and CI includes a frontend build job.

## Stack components — explicit mapping

| Spec component | Status / note |
| --- | --- |
| FastAPI + Python 3.11+ | Implemented |
| Next.js / TS / Tailwind | Scaffolded (`apps/frontend`) |
| Orchestration: **LangGraph** | **Deviation** — replaced by an explicit, typed in-process plan executor (`orchestrator` + `workflow_service`). Justification: a transparent, fully-testable, dependency-light control flow with an auditable plan; the agent interfaces would allow a LangGraph adapter later without changing agents. |
| Workflow engine: **Temporal/Camunda** | Documented seam (`apps/worker`, `WORKFLOW_BACKEND=temporal`); in-process default so no cluster is needed to run/test. |
| PostgreSQL | Implemented (prod target); SQLite for dev/tests via the same models. |
| pgvector | Documented seam (`VECTOR_BACKEND=pgvector`); in-memory cosine default. |
| Redis | Configured in compose + settings; not yet used for app-level caching/rate-limiting (a `security_rate_limit_per_minute` setting exists as a hook). **Partial.** |
| MinIO / S3 | Documented seam (`S3Storage`, `[storage]` extra); local-FS default. |
| Keycloak (OIDC) | Documented seam + realm export; local JWT default. |
| Prometheus / Grafana | Implemented (metrics endpoint, scrape config, provisioned dashboard). |
| Docker | Implemented (backend + worker + frontend Dockerfiles, compose). |
| Kubernetes | Scaffolded (`infrastructure/k8s`). |

## Summary

The backend platform — model router, agents, HITL workflow engine, data model, API,
auth/RBAC, audit/observability, migrations, and tests — is **implemented and verified**.
Production integrations (Temporal, pgvector, S3/MinIO, OIDC) are **documented seams**
behind stable interfaces with portable defaults; the frontend, Kubernetes manifests,
and the release-deploy step are **scaffolded**. Every deviation above exists to satisfy
the explicit requirement that the system be a real, runnable, tested platform rather
than a toy demo, while keeping the road to production short and obvious.
