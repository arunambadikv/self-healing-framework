#!/usr/bin/env bash
# One-time checklist: Playwright MCP in Cursor + repo paths for registry auto-update.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Playwright Healing: MCP agent setup =="
echo ""

if ! command -v npx >/dev/null 2>&1; then
  echo "WARN: npx not found. Install Node.js 18+ for Playwright MCP."
else
  echo "OK: npx $(npx --version 2>/dev/null || true)"
fi

if [[ ! -f "${ROOT}/.cursor/mcp.json" ]]; then
  echo "WARN: missing ${ROOT}/.cursor/mcp.json"
else
  echo "OK: .cursor/mcp.json present (reference config for Cursor)"
fi

mkdir -p artifacts/mcp-repair-bundles/resolved
echo "OK: artifacts/mcp-repair-bundles/resolved/"

cat <<'EOF'

--- Cursor (one-time) ---

1. Open this repo in Cursor.
2. Settings → MCP → Add server (or copy .cursor/mcp.json):
     command: npx
     args: ["@playwright/mcp@latest"]
   Optional headless: add "--headless" to args.
3. Confirm the server shows as connected (green) in MCP panel.
   In Agent chat it is usually named "playwright" or "user-playwright".

--- End-to-end workflow ---

A) Run raw tests (auto-creates MCP prompts):
     pytest tests/test_pure_playwright_example.py -s

B) In Cursor Agent, run repair for pending keys:
     Repair all pending keys in artifacts/mcp-repair-bundles/prompts/
     using Playwright MCP. Write resolved JSON per AGENTS.md.

   Or one key:
     Repair auto.pure_playwright_example.click_button_click_me_green
     using Playwright MCP per artifacts/mcp-repair-bundles/prompts/

C) Apply agent output to registry:
     python -m healing.mcp_apply --apply-all --apply
     pytest tests/ -q
     python -m healing.ci_gates

--- Optional: auto-apply draft keys without MCP (lowest quality) ---

     HEALING_REGISTRY_AUTO_APPLY=1 pytest tests/test_pure_playwright_example.py

Use MCP review for stable locators before production CI.

EOF

PENDING=$(find artifacts/mcp-repair-bundles/prompts -name '*.md' 2>/dev/null | wc -l)
RESOLVED=$(find artifacts/mcp-repair-bundles/resolved -name '*.json' 2>/dev/null | wc -l)
echo "Pending MCP prompts: ${PENDING}"
echo "Resolved patches ready to apply: ${RESOLVED}"
