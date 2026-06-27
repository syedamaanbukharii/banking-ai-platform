# API Reference

Base path: `/api/v1`. Interactive docs at `/docs` (Swagger UI) and the schema at
`/openapi.json`.

## Authentication

Two ways to authenticate, both carrying a signed JWT:

- **Bearer header**: `Authorization: Bearer <access_token>`.
- **HttpOnly cookie**: `login` also sets `access_token` and `refresh_token` cookies for
  browser clients (sent automatically with `credentials: "include"`).

Tokens are short-lived access tokens plus longer-lived refresh tokens. `refresh`
issues a fresh pair (rotation). In OIDC mode the API validates tokens issued by the
IdP (Keycloak) instead of issuing them locally — see `docs/auth.md`.

## Authorization

Endpoints require fine-grained **permissions** (not roles). The caller's roles resolve
to a permission set; missing permissions yield `403` with code `authorization_error`.
The permission matrix is in `docs/auth.md`.

## Endpoints

| Method | Path | Permission | Notes |
| --- | --- | --- | --- |
| POST | `/auth/login` | — | Email+password → token pair (+ cookies) |
| POST | `/auth/refresh` | — | Body or cookie refresh token → new pair |
| GET | `/auth/me` | (any authenticated) | Current principal: roles + permissions |
| POST | `/documents/upload` | `document:upload` | multipart; ingests, chunks, embeds, indexes |
| GET | `/documents/{id}` | `document:read` | Document metadata |
| POST | `/workflows/start` | `workflow:start` | Runs the plan; may await approval |
| GET | `/workflows` | `workflow:read` | Manual-review queue (paginated) |
| GET | `/workflows/{id}` | `workflow:read` | Workflow + agent runs + approvals + tasks |
| POST | `/workflows/{id}/approve` | `workflow:approve` | HITL approve → completed |
| POST | `/workflows/{id}/reject` | `workflow:reject` | HITL reject |
| POST | `/workflows/{id}/escalate` | `workflow:escalate` | HITL escalate |
| GET | `/agents/{agent_name}/runs` | `agent:read` | Agent-run history (paginated) |
| GET | `/search` | `search:read` | Semantic search over indexed chunks |
| GET | `/audit/logs` | `audit:read` | Append-only audit log (paginated, filterable) |
| GET | `/admin/router` | `admin:read` | Active routing policy + provider chain |
| GET | `/health` | — | Liveness |
| GET | `/ready` | — | Readiness (checks the database) |
| GET | `/metrics` | — | Prometheus metrics (if enabled) |

## Workflow types

`workflow_type` is one of: `document_intelligence`, `kyc`, `fraud_review`,
`compliance`, `audit_evidence`, `loan`. `input_payload` is a free-form JSON object
shaped to the agents the plan runs (see `docs/agents.md` for each agent's expected
fields). KYC, fraud, and loan are approval-gated by default.

Example — start a KYC workflow:

```json
POST /api/v1/workflows/start
{
  "workflow_type": "kyc",
  "input_payload": {
    "kind": "identity",
    "text": "Full Name: Jane Doe\nDocument Number: X1",
    "profile": {"full_name": "Jane Doe", "date_of_birth": "1990-01-02",
                 "country": "US", "document_number": "X1"},
    "document_fields": {"full_name": "Jane Doe", "document_number": "X1"}
  }
}
```

## Error envelope

Every error returns a stable, machine-readable envelope:

```json
{ "error": { "code": "invalid_workflow_state", "message": "…", "details": { } } }
```

Common codes: `validation_error` (422), `authentication_error` (401),
`authorization_error` (403), `not_found` (404), `invalid_workflow_state` (409),
`llm_provider_error` (502), `model_router_error` (503), `internal_error` (500).

## Pagination

List endpoints accept `page` (≥1) and `page_size` (1–200) and return:

```json
{ "items": [ … ], "meta": { "page": 1, "page_size": 20, "total": 57, "total_pages": 3 } }
```

## Request tracing

Every response carries an `X-Request-ID` (echoed from the request or generated). The
same id is bound to all structured logs and written into audit records for correlation.
