#!/usr/bin/env bash
# Regenerate backend models and frontend types from the JSON Schema (AGENTS.md §5).
#
#   ./scripts/gen_types.sh            rewrite both generated files
#   ./scripts/gen_types.sh --check    exit 1 when either file is stale (CI)
#
# The generator is stdlib-only: it needs no backend or frontend dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/gen_types.py "$@"
