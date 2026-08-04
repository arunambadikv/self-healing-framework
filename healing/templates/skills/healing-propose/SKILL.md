---
name: healing-propose
description: Process unhandled failure reports (healer-artifacts/failures/F-*.json) with Playwright MCP and create healing-queue patch proposals (P-*.json/.md) with architecture_updates for pages/*.py. Use when the user runs /healing-propose after test failures.
disable-model-invocation: true
---

# Healing Propose (MCP + Agent)

## Objective

Turn new failures into reviewable patch proposals without applying changes.

## Steps

1. Run: `python -m healing.architecture_scan` if manifest is missing or stale.
2. Run: `python -m healing.pom_propose --list` to see unprocessed failures.
3. For each unprocessed `F-*` failure, follow **`/playwright-locator-repair`**:
   - Read failure JSON/MD and architecture manifest
   - Playwright MCP: navigate + snapshot
   - Write `healer-artifacts/healing-queue/patches/P-<id>.json` and `.md`
4. Or batch stubs: `python -m healing.pom_propose --process-all` then complete TODOs via MCP.
5. After MCP completes `P-*.json`, promote to review queue:
   ```bash
   python -m healing.healing_review --promote P-<id>
   # or: python -m healing.healing_review --promote-all
   ```
   Use `--promote-all` before `--list` when skill-only MCP repair left patches in `awaiting_agent`.

## Rules

- Do not apply patches — human uses `/healing-review`.
- Do not weaken assertions or skip tests.
