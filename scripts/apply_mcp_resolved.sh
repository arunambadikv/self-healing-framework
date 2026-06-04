#!/usr/bin/env bash
# Apply all agent-written resolved/*.json files to locator_registry.yaml.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

APPLY="${APPLY:-1}"
ARGS=(--apply-all)
if [[ "$APPLY" != "1" ]]; then
  ARGS=(--apply-all) # dry-run unless --apply passed via env
fi
if [[ "${1:-}" == "--dry-run" ]]; then
  "$PYTHON" -m healing.mcp_apply --apply-all
  exit 0
fi

"$PYTHON" -m healing.mcp_apply --apply-all --apply
"$PYTHON" -m healing.registry_lint
"$PYTHON" -m healing.ci_gates --skip-reports
