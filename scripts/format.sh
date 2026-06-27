#!/usr/bin/env bash
# Auto-format and auto-fix lint where possible. Usage: ./scripts/format.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check apps tests migrations --fix
black apps tests migrations
