#!/usr/bin/env bash
# Phase A: registry lint + smart test policy + healing report thresholds.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

echo "== Architecture manifest =="
"$PYTHON" -m pomhealer.architecture_scan

echo ""
echo "== CI gates (POM policy + healing queue) =="
"$PYTHON" -m pomhealer.ci_gates "$@"
