# Security

This platform handles sensitive banking data and makes risk-relevant decisions, so
security and auditability are first-class. This document summarises the model and the
hardening steps for production.

## Decision safety (HITL)

High-risk outcomes (KYC results, fraud blocks, lending decisions) are never finalised
autonomously. The orchestrator marks those workflows approval-gated, and an agent can
additionally raise `requires_human_review`. A human with the correct permission must
approve before the workflow completes; the decision, the deciding user, and the reason
are persisted.

## AuthN / AuthZ

- JWTs are signed (HS256 in local mode) and validated for `exp`/`iat`/`sub` and token
  `type`. Refresh rotates the pair.
- The app refuses to start outside local with a missing/placeholder/short JWT secret,
  and requires the OIDC client secret in OIDC mode.
- Authorization is permission-based; unknown roles in a token are ignored.
- Browser sessions use HttpOnly cookies (`SameSite=Lax`); set `SECURITY_COOKIE_SECURE`
  and a real cookie domain behind TLS.

## Secrets

No secrets are committed. All credentials are environment-driven (`.env.example`
documents the keys with placeholders). In Kubernetes, provide secrets via a secrets
manager (Sealed Secrets / External Secrets / Vault); `secret.example.yaml` is a template
only. Local-dev credentials in this repo are placeholders and must never be reused.

## Audit log

`audit_logs` is **append-only by convention**: the service layer only inserts, never
updates or deletes, and the table exposes no ORM relationships that would cascade a
delete into it. Each entry records actor, action, resource, outcome, request id, and
non-sensitive context.

For production, enforce immutability at the database layer as defence in depth:

- Grant the application role `INSERT, SELECT` on `audit_logs` only (no `UPDATE`/`DELETE`).
- Optionally add `BEFORE UPDATE/DELETE` triggers that raise, and/or ship audit rows to
  append-only/WORM storage.

## Redaction

Two layers scrub sensitive values so they never land in logs or the audit trail:

- The structlog processor redacts keys matching sensitive patterns (password, secret,
  token, authorization, api_key, ssn, card_number, account_number, jwt, …).
- The audit service redacts known-sensitive keys in `context` before persistence.

The model router records token counts and provider/model/latency, not prompt or
completion content, keeping sensitive payloads out of telemetry.

## Model routing safety

The active policy and provider chain are explicit and exposed (to admins) at
`/admin/router`. Fallbacks are recorded with a reason. The `echo` stub provider is only
ever added in local environments, so production cannot silently answer with a
non-model stub.

## Input handling

- Pydantic schemas validate and bound all request bodies and query parameters.
- File uploads are size-capped; file bytes are stored in object storage, never in the
  database. The local-FS adapter guards against path traversal in storage keys.
- Errors return a structured envelope with stable codes and no stack traces.

## Dependency & static analysis

CI runs `bandit` (security linter) and the type checker; pin and scan dependencies in
your pipeline (e.g. `pip-audit`) and enable Dependabot. The few `# nosec` annotations
are limited to verified false positives (token *type* labels and the placeholder-secret
sentinel) and are documented inline.

## Reporting

Use the repository's security policy / private disclosure channel for vulnerabilities;
do not file public issues for security reports.
