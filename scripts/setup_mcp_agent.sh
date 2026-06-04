#!/usr/bin/env bash
# One-time checklist: Playwright MCP in Cursor + POM healing paths.
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

mkdir -p artifacts/failures artifacts/healing-queue/patches artifacts/architecture
echo "OK: artifact directories"

cat <<'EOF'

--- Cursor (one-time) ---

1. Open repo in Cursor.
2. Settings → MCP → Add server from .cursor/mcp.json:
   command: npx
   args: ["@playwright/mcp@latest"]
3. Confirm MCP connected in the panel.

--- POM healing workflow ---

  pytest tests/ -v
  python -m healing.architecture_scan
  python -m healing.pom_propose --process-all
  # Agent: complete patches in artifacts/healing-queue/patches/ (see AGENTS.md)
  python -m healing.healing_review --list
  python -m healing.healing_review --patch P-<id> --decision heal

See AGENTS.md for slash skills: /architecture-discovery, /healing-propose, /healing-review

EOF
