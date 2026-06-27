# Testing

The suite is deterministic and fully offline: no network, no external services. The LLM
path resolves to a fake/`echo` provider, the database is in-memory SQLite, the vector
store is in-memory, and storage is a temp directory.

## Run

```bash
pytest                              # everything
pytest --cov=banking_ai --cov-report=term-missing   # with coverage (gate: 70%, currently ~90%)
pytest tests/unit                   # fast unit tests
pytest tests/integration            # service + DB tests
pytest tests/e2e                    # full API flows over an in-process ASGI client
pytest -k "fraud or kyc"            # filter by keyword
```

## Layers

- **Unit** (`tests/unit/`): the model router (selection, fallback on error/unavailable,
  all-fail, per-attempt telemetry, cost) and every agent's deterministic logic with a
  mocked/fake LLM.
- **Integration** (`tests/integration/`): services against a real in-memory database —
  seeding/auth, document ingest + retrieve, the HITL workflow (approve/reject/queue,
  invalid-transition guard, failure marking), and the DB-backed router observer
  persisting `model_calls`.
- **End-to-end** (`tests/e2e/`): the real FastAPI app (running its lifespan: engine
  init, table creation, dev-admin seeding) driven via httpx ASGI transport against a
  temporary SQLite database — health/readiness, login + RBAC denial, refresh rotation,
  document upload → search, the full KYC approve flow, the fraud reject flow, the
  invalid-state 409, audit logging, and the router-config endpoint.

## Fixtures

`tests/conftest.py` provides an isolated in-memory async engine/session per test and a
temp storage root. `tests/e2e/conftest.py` boots the app over a temp SQLite DB with its
lifespan, exposes an httpx client, and provides `login_admin` / `auth_header` helpers.

## Determinism notes

- The `HashingEmbedder` is a fixed hashing projection, so retrieval ranking is stable.
- Agents accept injectable inputs where time matters (e.g. KYC `today`).
- The `echo` provider and `FakeProvider` make model-backed agents reproducible.

## Quality gate

CI runs ruff (lint), black (format check), mypy (strict), bandit (security), the test
suite with coverage, and an Alembic upgrade/downgrade check. Run them locally with:

```bash
ruff check apps tests migrations
black --check apps tests migrations
mypy apps/backend/banking_ai
bandit -r apps/backend/banking_ai -q
```
