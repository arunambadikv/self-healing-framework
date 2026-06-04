#!/usr/bin/env bash
# Phase B: MCP-assisted repair bundles from healing reports.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

INSPECT="${INSPECT:-0}"
ARGS=()
if [[ "$INSPECT" == "1" ]]; then
  ARGS+=(--inspect)
fi

"$PYTHON" -m healing.mcp_repair_pipeline "${ARGS[@]}" "$@"
