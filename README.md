# Enterprise Agentic AI Platform for Banking Operations

A production-oriented backend platform where AI agents **assist** banking operations
(document intelligence, KYC/AML, fraud review, compliance Q&A, loan affordability)
while **high-risk decisions remain human-approved**. The system is auditable end to
end: every model call, agent run, and approval is recorded.

> This is not a chatbot. It is an agentic workflow platform with a human-in-the-loop
> (HITL) approval path, role-based access control, and a model router that fails over
> between an online model (Groq) and a local model (Gemma) without ever silently
> switching.

## Highlights

- **Model router** with an explicit, auditable provider chain and offline fallback;
  one `model_calls` record per attempt (including failures).
- **Specialised agents** (document, KYC, fraud, compliance/RAG, summarization,
  retrieval, loan, notification, audit, orchestrator) — each independently testable,
  with deterministic logic kept out of the model path.
- **HITL workflow engine** — a guarded state machine: `running → awaiting_approval →
  approved/rejected/escalated → completed`, with a manual-review queue.
- **RBAC** with fine-grained permissions; the API authorizes on permissions, not roles.
- **JWT auth** (local mode) with an OIDC/Keycloak seam; HttpOnly-cookie or Bearer.
- **Append-only audit log**, cost tracking, and Prometheus metrics.
- **Runs with zero external dependencies** for local dev/tests (SQLite, in-memory
  vector store, local-FS storage, deterministic `echo` model), and scales up to
  Postgres + pgvector + MinIO + Keycloak + Temporal via configuration.

See `IMPLEMENTATION_STATUS.md` for a precise, honest map of what is fully implemented
versus scaffolded/documented, with justifications.

## Quickstart (no Docker, no API keys)

Requires Python 3.11+.

```bash
# From the repository root
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the full test suite (unit + integration + e2e), all offline
pytest

# Start the API (auto-creates SQLite tables and seeds a dev admin in local env)
uvicorn banking_ai.main:app --reload --app-dir apps/backend
# open http://localhost:8000/docs
```

Default dev admin (local only): `admin@local.dev` / `Admin123!Local`.

A 60-second tour of the HITL path:

```bash
# 1) Log in
TOKEN=$(curl -s localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@local.dev","password":"Admin123!Local"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2) Start a fraud-review workflow (high-risk -> awaits approval)
WF=$(curl -s localhost:8000/api/v1/workflows/start -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"workflow_type":"fraud_review","input_payload":{"transaction":{"amount":50000,"beneficiary_country":"XX","account_age_days":2}}}')
echo "$WF" | python -m json.tool   # status == "awaiting_approval"

# 3) Approve or reject it (decision is audited)
WID=$(echo "$WF" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s localhost:8000/api/v1/workflows/$WID/reject -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"reason":"confirmed fraud"}' | python -m json.tool
```

## Quickstart (Docker Compose — closer to prod)

```bash
cp .env.example .env          # adjust as needed; add GROQ_API_KEY to use the online model
docker compose up --build
# backend: http://localhost:8000/docs   grafana: http://localhost:3001   keycloak: http://localhost:8080
```

The backend runs `alembic upgrade head` on start. To enable the online model, set
`GROQ_API_KEY` in `.env`; otherwise the router falls back to the local model and,
in local env only, to the deterministic `echo` provider so the stack always runs.

## Repository map

```
apps/
  backend/banking_ai/      # the deployable Python package
    core/                  # config, logging, errors, RBAC, security (JWT/principal)
    db/                    # SQLAlchemy base, session, models (18 tables)
    ai/                    # model router, providers (groq/local/echo), vector store, cost
    agents/                # specialised agents + orchestrator
    services/              # workflow (HITL), documents, audit, storage, seed, observer
    api/                   # FastAPI app: deps, middleware, error handlers, v1 routers
    prompts/               # versioned prompt templates + registry
    main.py                # app factory + entrypoint
  worker/                  # Temporal worker scaffold (shares the agent executor)
  frontend/                # Next.js operator console scaffold (HITL review)
migrations/                # Alembic (async env + initial migration)
infrastructure/            # Dockerfiles, k8s, keycloak realm, prometheus, grafana
tests/                     # unit, integration, e2e (all offline, deterministic)
docs/                      # architecture, api, agents, auth, deployment, testing, ...
```

## Documentation

- `docs/architecture.md` — layered design, data model, key decisions and trade-offs
- `docs/api.md` — endpoints, auth, error envelope, pagination
- `docs/agents.md` — each agent's responsibility, I/O, and determinism
- `docs/auth.md` — local JWT vs OIDC/Keycloak, RBAC permission matrix
- `docs/deployment.md` — Docker Compose, Kubernetes, production checklist
- `docs/testing.md` — test strategy and how to run subsets
- `docs/security.md` — threat model, secrets, audit, redaction
- `docs/contributing.md` — toolchain, conventions, pre-commit

## License

See repository license. Local-dev credentials in this repo are placeholders and must
never be used outside local development.
# banking-ai-platform
