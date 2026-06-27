# Architecture

## Principles

1. **AI assists; humans decide the risky calls.** Agents produce analysis,
   extractions, scores, and drafts. Anything high-risk (KYC outcome, fraud block,
   lending decision) is routed to a human with the right permission before it takes
   effect.
2. **Everything is auditable.** Every model call, agent run, workflow transition, and
   human decision is persisted. Logs and audit context are redacted.
3. **Deterministic where it matters.** The logic on the decision path (validation,
   risk scoring, consistency checks) is rule-based and unit-tested; models are used
   for summarization and grounded Q&A, never as an opaque approver.
4. **Runnable by default, scalable by configuration.** The same code runs on SQLite +
   in-memory adapters (dev/tests) or Postgres + pgvector + MinIO + Keycloak + Temporal
   (production), switched by environment variables.

## Layered design

```
            ┌─────────────────────────────────────────────┐
  clients → │  API (FastAPI): routers, deps, middleware,    │
            │  exception handlers, OpenAPI, metrics          │
            ├─────────────────────────────────────────────┤
            │  Services (use-cases): workflow (HITL),        │
            │  documents, audit, storage, seed, observer     │
            ├───────────────┬───────────────┬───────────────┤
            │  Agents        │  AI infra      │  Auth/RBAC    │
            │  (orchestrator │  (model router │  (JWT,        │
            │   + specialists)│  + providers, │   principal,  │
            │                │  vector store) │   permissions)│
            ├───────────────┴───────────────┴───────────────┤
            │  Persistence (SQLAlchemy async, 18 tables)     │
            ├─────────────────────────────────────────────┤
            │  Cross-cutting: config, structured logging,    │
            │  error envelope                                │
            └─────────────────────────────────────────────┘
```

Dependencies point downward. Agents depend on AI infra (router, vector store) but not
on services or the API. Services compose agents and persistence. The API composes
services. This keeps each layer independently testable.

## Model router (the centrepiece)

The router takes an **ordered list of providers** and a policy, and tries each in turn:

- It checks `is_available()` (credentials/offline awareness), then calls `complete()`.
- On `LLMProviderError` it records a failure and moves to the next provider.
- On success it sets `used_fallback`/`fallback_reason` and records the call.
- If all providers fail it raises `ModelRouterError`.

It emits **one `ModelCallRecord` per attempt** — including failures — to an observer.
The DB-backed observer persists these to `model_calls` (+ `cost_tracking` for priced
successes) in its own short-lived session, so telemetry is durable and never breaks
routing (observer exceptions are swallowed and logged).

Policies (`LLM_ROUTER_POLICY`): `online_only` → `[primary]`; `offline_only` →
`[fallback]`; `prefer_online` → `[primary, fallback]`. In **local** environments only,
a deterministic `echo` provider is appended as a last resort so the platform runs with
zero credentials. It is never appended outside local, so production cannot silently
serve a stub in place of a real model.

## HITL workflow engine

`WorkflowService.start` asks the orchestrator for a **plan** (which agents to run, and
whether the workflow is approval-gated), runs each step in-process recording an
`agent_runs` row, then either completes the workflow or parks it in
`awaiting_approval` with a pending `approvals` row. A workflow also becomes
approval-gated if any agent flags `requires_human_review` (e.g. fraud risk ≥ HIGH).

Decisions (`approve`/`reject`/`escalate`) are **guarded transitions**: they apply only
to a workflow in `awaiting_approval`/`escalated`, otherwise raise
`WorkflowStateError` (HTTP 409, code `invalid_workflow_state`). Each decision records
the deciding user, reason, and an audit entry. Approval drives the workflow to
`completed`.

The default executor is in-process (`WORKFLOW_BACKEND=inprocess`). A Temporal worker
(`apps/worker`) is the production seam; it reuses the same `AgentExecutor`, so the
business logic is shared — Temporal only adds durability and orchestration.

## Data model (18 tables)

- **IAM**: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`
  (normalised many-to-many).
- **Documents**: `documents` (metadata + `storage_key`; file bytes live in object
  storage, never in the DB), `document_chunks`, `embeddings_metadata` (vector stored as
  JSON for portability; pgvector mirror in production).
- **Workflow**: `applications`, `workflows`, `agent_runs`, `approvals`, `task_status`.
- **Observability/governance**: `audit_logs` (append-only), `model_calls`,
  `cost_tracking`, `feedback`, `incidents`.

UUID primary keys map to native `uuid` on Postgres and `CHAR(32)` on SQLite; JSON uses
the dialect-agnostic type (upgradeable to `JSONB` on Postgres). Timestamps default in
Python for deterministic, dialect-independent behaviour.

## Key decisions and trade-offs

- **Vector store**: a `VectorStore` protocol with an in-memory cosine implementation
  (dev/tests) and a documented `PgVectorStore` seam. A deterministic `HashingEmbedder`
  (hashed bag-of-words, L2-normalised) keeps retrieval reproducible offline; production
  swaps in a real sentence-embedding model behind the same protocol. This avoids a
  native pgvector build and a model download in the default path while keeping the
  interface identical.
- **Workflow engine**: pluggable executor with an in-process default and a Temporal
  seam, so `docker compose up` and the tests need no Temporal cluster.
- **Password hashing**: `pbkdf2_sha256` (pure-Python) to avoid native bcrypt build
  issues in constrained environments; the `CryptContext` makes swapping schemes a
  one-line change.
- **`echo` provider**: a deterministic, no-network, no-key model stub used only as a
  local last resort so the platform is runnable end to end without secrets.
- **Package layout**: `agents/` and `services/` live inside the deployable
  `banking_ai` package for import hygiene; the spec's directory sketch is treated as
  illustrative. The vector store lives in `ai/` (not `services/`) to keep the agent →
  infra dependency direction clean and avoid an import cycle.

See `IMPLEMENTATION_STATUS.md` for the full implemented/scaffolded/documented matrix.
