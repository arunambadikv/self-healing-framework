#!/usr/bin/env bash
# One-time checklist: Playwright MCP in Cursor + POM pomhealer paths.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Playwright POM Healing: MCP setup =="

if command -v npx >/dev/null 2>&1; then
  echo "OK: npx $(npx --version 2>/dev/null || true)"
else
  echo "WARN: Install Node.js 18+ for Playwright MCP."
fi

[[ -f "${ROOT}/.cursor/mcp.json" ]] && echo "OK: .cursor/mcp.json" || echo "WARN: missing .cursor/mcp.json"

mkdir -p pomhealer-artifacts/failures pomhealer-artifacts/pomhealer-queue/patches pomhealer-artifacts/architecture
echo "OK: artifact directories"

cat <<'EOF'

--- Cursor (one-time) ---

1. Open repo in Cursor.
2. Settings → MCP → Add server from .cursor/mcp.json:
   command: npx
   args: ["@playwright/mcp@0.0.79"]
3. Confirm MCP connected in the panel.

--- POM pomhealer workflow ---

  pytest tests/ -v
  python -m pomhealer.architecture_scan
  python -m pomhealer.pom_propose --process-all
  python -m pomhealer.mcp_propose_runner --process-all   # needs POMHEALER_LLM_PROVIDER + key
  # Completed P-* files live in pomhealer-artifacts/pomhealer-queue/patches/ until review
  python -m pomhealer.review --list
  python -m pomhealer.review --patch P-<id> --decision heal
  # After heal/skip, json/md/agent-task move to applied/ or skipped/

See AGENTS.md for slash skills: /architecture-discovery, /pomhealer-propose, /pomhealer-review

EOF
