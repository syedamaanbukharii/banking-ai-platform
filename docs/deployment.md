# Deployment

## Local (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

Services: backend (`:8000`), Postgres (`:5432`), Redis (`:6379`), MinIO
(`:9000`/`:9001`), Keycloak (`:8080`), Prometheus (`:9090`), Grafana (`:3001`), and a
worker. The backend runs `alembic upgrade head` before serving. Set `GROQ_API_KEY` in
`.env` to enable the online model; otherwise the router falls back to the local model
(and, in local env, to `echo`).

Compose credentials are **local-dev only**. Never reuse them elsewhere.

## Configuration

All configuration is environment-driven (12-factor); see `.env.example` for the full
list. Notable switches:

- `APP_ENV` (`local`/`staging`/`production`) — gates dev seeding and secret enforcement.
- `DATABASE_URL` — `postgresql+asyncpg://…` in prod; SQLite for dev/tests.
- `SECURITY_AUTH_MODE` — `local` or `oidc`.
- `LLM_ROUTER_POLICY` — `prefer_online` / `online_only` / `offline_only`.
- `VECTOR_BACKEND` — `memory` (default) or `pgvector` (production seam).
- `WORKFLOW_BACKEND` — `inprocess` (default) or `temporal`.
- `STORAGE_USE_LOCAL_FS` — `true` (dev) or `false` (S3/MinIO).

## Database migrations

```bash
alembic upgrade head      # apply
alembic downgrade base    # roll back
alembic revision --autogenerate -m "change"   # after editing models
```

The async `migrations/env.py` reads `DATABASE_URL` from settings; no credentials are in
version control. The initial migration is verified to upgrade and downgrade on SQLite;
on Postgres, enable the `pgvector` extension separately if `VECTOR_BACKEND=pgvector`.

## Kubernetes (scaffold)

`infrastructure/k8s/` contains a documented starting point: namespace, ConfigMap,
Secret template, and a non-root, probed, resource-bounded backend Deployment + Service.
See `infrastructure/k8s/README.md`. Provide secrets via your secrets manager (Sealed
Secrets / External Secrets / Vault) — never commit real values.

Apply order:

```bash
kubectl apply -f infrastructure/k8s/namespace.yaml
kubectl apply -f infrastructure/k8s/configmap.yaml
kubectl apply -f infrastructure/k8s/secret.example.yaml   # replace with a real source
kubectl apply -f infrastructure/k8s/backend-deployment.yaml
kubectl apply -f infrastructure/k8s/backend-service.yaml
```

## CI/CD

- **CI** (`.github/workflows/ci.yml`): ruff, black, mypy, bandit, pytest+coverage, an
  Alembic upgrade/downgrade check, a backend image build, and a frontend build.
- **Release** (`.github/workflows/release.yml`): on a `vX.Y.Z` tag, builds and pushes
  backend/worker/frontend images to GHCR, deploys to the `staging` environment, then to
  `production` — which is gated by required reviewers configured on the GitHub
  Environment (the human approval gate). Wire your `kubectl`/`helm`/Argo step into the
  deploy jobs.

## Production seams (not on the default runtime path)

These are implemented as documented interfaces with in-process/portable defaults so the
repo runs and tests pass offline; swapping them in is configuration, not code surgery:

- **Workflow engine → Temporal**: `apps/worker` reuses the shared `AgentExecutor`.
- **Vector store → pgvector**: `PgVectorStore` behind the `VectorStore` protocol;
  swap the embedder for a real model behind the `Embedder` protocol.
- **Object storage → S3/MinIO**: `S3Storage` behind the `ObjectStorage` protocol
  (`[storage]` extra provides `boto3`).
- **Auth → OIDC/Keycloak**: token verification seam in `core/security.py`; realm export
  in `infrastructure/keycloak`.

## Production checklist

- Set a strong `SECURITY_JWT_SECRET` (≥32 chars) or use OIDC; the app refuses
  placeholder secrets outside local.
- Managed Postgres (with `pgvector` if used), Redis, and S3/MinIO; run migrations on
  deploy.
- Terminate TLS at the ingress; set `SECURITY_COOKIE_SECURE=true` and a real cookie
  domain; restrict `APP_CORS_ORIGINS`.
- Scrape `/metrics`; ship structured logs; alert on `model_calls` failure/fallback
  rates and on workflows stuck in `awaiting_approval`.
- Harden `audit_logs` immutability at the database layer (see `docs/security.md`).
- Add Ingress/TLS, HPA, NetworkPolicies, and PodDisruptionBudgets for the cluster.
