---
name: pomhealer-propose
description: Process unhandled failure reports (pomhealer-artifacts/failures/F-*.json) with Playwright MCP and create pomhealer-queue patch proposals (P-*.json/.md) with architecture_updates for pages/*.py. Use when the user runs /pomhealer-propose after test failures.
disable-model-invocation: true
---

# Healing Propose (MCP + Agent)

## Objective

Turn new failures into reviewable patch proposals without applying changes.

## Steps

1. Run: `python -m pomhealer.architecture_scan` if manifest is missing or stale.
2. Run: `python -m pomhealer.pom_propose --list` to see unprocessed failures.
3. For each unprocessed `F-*` failure, follow **`/playwright-locator-repair`**:
   - Read failure JSON/MD and architecture manifest
   - Playwright MCP: navigate + snapshot
   - Write `pomhealer-artifacts/pomhealer-queue/patches/P-<id>.json` and `.md`
4. Or batch stubs: `python -m pomhealer.pom_propose --process-all` then complete TODOs via MCP.
   CLI/CI path (uses `POMHEALER_LLM_PROVIDER` + key from `.env`):
   ```bash
   python -m pomhealer.mcp_propose_runner --process-all
   ```
   OpenAI / Gemini / Groq propose with Playwright MCP plus `read_workspace_file` /
   `write_workspace_file` (patches under `pomhealer-artifacts/pomhealer-queue/patches/` only).
   Do not invent tool names such as `browser_open_file`.
5. After MCP completes `P-*.json`, promote to review queue:
   ```bash
   python -m pomhealer.review --promote P-<id>
   # or: python -m pomhealer.review --promote-all
   ```
   Use `--promote-all` before `--list` when skill-only MCP repair left patches in `awaiting_agent`.

## Rules

- Do not apply patches — human uses `/pomhealer-review`.
- Do not weaken assertions or skip tests.
