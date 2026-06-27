#!/usr/bin/env bash
# Run the API locally (SQLite, auto-seeded dev admin). Usage: ./scripts/dev.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV="${APP_ENV:-local}"
exec uvicorn banking_ai.main:app --reload --app-dir apps/backend
