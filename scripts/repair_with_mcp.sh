#!/usr/bin/env bash
# Full MCP repair workflow: tests → bundles → print Cursor instructions.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

echo "== Run tests =="
"$PYTHON" -m pytest tests/ -q

echo ""
echo "== CI gates =="
"$PYTHON" -m healing.ci_gates

echo ""
echo "== Generate MCP repair bundles =="
"$PYTHON" -m healing.mcp_repair_pipeline "$@"

echo ""
echo "== Cursor MCP repair =="
echo "1. Open AGENTS.md and artifacts/mcp-repair-bundles/prompts/*.md in Cursor Agent"
echo "2. Ensure Playwright MCP is connected (see .cursor/mcp.json)"
echo "3. Agent runs browser_navigate + browser_snapshot and writes:"
echo "   artifacts/mcp-repair-bundles/resolved/<key>.json"
echo "4. Apply: python -m healing.mcp_apply --key <key> --apply"
