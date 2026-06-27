#!/usr/bin/env bash
# Run the full local quality gate (mirrors CI). Usage: ./scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ruff =="
ruff check apps tests migrations
echo "== black --check =="
black --check apps tests migrations
echo "== mypy =="
mypy apps/backend/banking_ai
echo "== bandit =="
bandit -r apps/backend/banking_ai -q
echo "== pytest (+coverage) =="
pytest --cov=banking_ai --cov-report=term-missing
echo "All checks passed."
