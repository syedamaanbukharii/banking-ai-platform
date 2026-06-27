# Contributing

## Toolchain

- Python 3.11+ (developed and tested on 3.12).
- Install with dev extras: `pip install -e ".[dev,storage,workflow]"`.
- Optional: `pre-commit install` to run the hooks on every commit.

## Local checks (run before pushing)

```bash
ruff check apps tests migrations          # lint
black apps tests migrations               # format
mypy apps/backend/banking_ai              # type-check (strict)
bandit -r apps/backend/banking_ai -q      # security
pytest                                    # tests (offline)
```

CI runs the same gate plus an Alembic upgrade/downgrade check and image builds.

## Conventions

- **Layering**: dependencies point downward (API → services → agents/AI infra →
  persistence → core). Don't import services from agents, or the API from services in
  the wrong direction.
- **Errors**: raise an `AppError` subclass; the API renders the envelope. Don't leak
  stack traces or raw exceptions to clients.
- **Typing**: full type hints; mypy is strict. Avoid `Any` except at true boundaries.
- **Logging**: use the structured logger (`get_logger`); never log secrets/PII — the
  redactor helps but don't rely on it for obviously sensitive values.
- **Determinism**: keep decision-path logic free of model calls and make it unit-test
  friendly (inject time/IDs). Model-backed code must be mockable.
- **Prompts**: add a new versioned template file (`name.vN.md`) rather than editing an
  existing version; point the agent at the new version.
- **Migrations**: change models, then `alembic revision --autogenerate`, review the
  generated file, and verify upgrade/downgrade.

## Adding an agent

1. Define typed input/output models and subclass `BaseAgent`.
2. Keep deterministic logic separate from any model call (inject the router only if
   needed).
3. Add it to `agents/__init__.py` and, if it participates in workflows, to the
   orchestrator plan and the `AgentExecutor` mapping.
4. Add unit tests covering the deterministic branches and any HITL flags.

## Adding an endpoint

1. Add a Pydantic request/response schema under `schemas/`.
2. Add the route to the relevant `api/v1/*.py` router, guarded by
   `require_permissions(...)`.
3. Return the structured error envelope on failure (raise `AppError` subclasses).
4. Add integration/e2e tests.

## Commit / PR

- Keep PRs focused; include tests for new behaviour.
- Ensure the full local gate passes; CI must be green to merge.
- Update the relevant doc and `IMPLEMENTATION_STATUS.md` when behaviour or scope changes.
