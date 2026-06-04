#!/usr/bin/env bash
# Phase A: registry lint + smart test policy + healing report thresholds.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

echo "== Registry lint =="
"$PYTHON" -m healing.registry_lint

echo ""
echo "== CI gates (policy + healing reports) =="
"$PYTHON" -m healing.ci_gates "$@"
