# Agent Instructions — Playwright Healing Framework

## Setup: MCP agent for registry auto-update

### One-time (Cursor + Playwright MCP)

```bash
bash scripts/setup_mcp_agent.sh
```

1. **Connect Playwright MCP in Cursor** — copy from `.cursor/mcp.json`:
   - Command: `npx`
   - Args: `@playwright/mcp@latest` (add `--headless` if needed)
2. **Verify** — MCP panel shows the server connected before using Agent.
3. **Enable project rule** — `.cursor/rules/playwright-mcp-repair.mdc` applies when you work on
   `artifacts/mcp-repair-bundles/**` or ask the agent to repair locators.

### Automatic pipeline (what runs without the agent)

| Step | Trigger | Output |
|------|---------|--------|
| Raw test run | `pytest` (no `smart` fixture) | `artifacts/raw-learning/reports/*.json` |
| Registry draft | same teardown | `artifacts/raw-learning/registry-drafts/*.yaml` |
| MCP task files | same teardown (`HEALING_RAW_MCP=1`, default) | `artifacts/mcp-repair-bundles/prompts/*.md` |

The agent step is **not** inside pytest — Cursor Agent + Playwright MCP inspects the live page and writes resolved patches.

### Agent step (Cursor)

After raw tests, open **Cursor Agent** and send:

```text
Process every pending file in artifacts/mcp-repair-bundles/prompts/.
For each key: CallMcpTool browser_navigate + browser_snapshot on the bundle base_url,
propose locators from the live page (not guesses), write
artifacts/mcp-repair-bundles/resolved/<semantic_key_with_underscores>.json
with LocatorPatchResult including patch YAML. Do not edit tests.
```

Single key example:

```text
Repair auto.pure_playwright_example.click_button_click_me_green using Playwright MCP
per artifacts/mcp-repair-bundles/prompts/auto_pure_playwright_example_click_button_click_me_green__add_semantic_key.md
```

**Resolved JSON shape** (agent output):

```json
{
  "proposal": {
    "classification": "add_semantic_key",
    "patch_type": "registry_only",
    "semantic_key": "auto.pure_playwright_example.click_button_click_me_green",
    "confidence": 0.9,
    "reason": "Verified via browser_snapshot",
    "patch": "auto.pure_playwright_example.click_button_click_me_green:\n  intent: ...\n  action: click\n  preferred:\n    - type: role\n      role: button\n      name: Click Me (Green)\n  fallback: []\n",
    "validation_command": "pytest tests/test_pure_playwright_example.py -q"
  }
}
```

### Apply agent patches to registry

```bash
python -m healing.mcp_apply --apply-all --apply
# or
bash scripts/apply_mcp_resolved.sh

pytest tests/ -q
python -m healing.ci_gates
```

Single key: `python -m healing.mcp_apply --key <semantic_key> --apply`

### Optional: Cursor Automation (hands-off agent)

Create a [Cursor Automation](https://cursor.com/docs/agent/automations) on a schedule or after git push:

- **Prompt:** same as the batch repair instruction above
- **Requirement:** Playwright MCP enabled for the automation environment
- **Post-step (local CI or hook):** `bash scripts/apply_mcp_resolved.sh`

### Smart tests (healing events → MCP bundles)

After each test using the `smart` fixture, if the healing report has **healed** or **failed** events (or patch suggestions), MCP bundles are generated automatically (default on):

```bash
pytest tests/test_demo_buttons_links.py -s
# [healing] smart-healing MCP: generated N bundle(s) ...
```

Disable: `HEALING_MCP_AUTO=0 pytest ...`  
Config: `healing_mcp.auto_after_test` in `healing/ci_gates_config.yaml`

Same agent + apply flow as raw learning:

```bash
# Agent: repair prompts in artifacts/mcp-repair-bundles/prompts/
bash scripts/apply_mcp_resolved.sh
```

Legacy env still works: `HEALING_TRIGGER_MCP_REPAIR=1` forces enable if `HEALING_MCP_AUTO` is unset.

```bash
HEALING_REGISTRY_AUTO_APPLY=1 pytest tests/test_pure_playwright_example.py
```

Uses captured selectors as-is — skip MCP review only for local experiments.

## MCP repair workflow (Cursor + Playwright MCP)

Playwright MCP should be connected in Cursor. Repo includes `.cursor/mcp.json` as a reference.

### 1. Generate repair bundles (after pytest)

```bash
pytest tests/ -q
python -m healing.mcp_repair_pipeline
```

Outputs:

- `artifacts/mcp-repair-bundles/prompts/*.md` — full Cursor agent task
- `artifacts/mcp-repair-bundles/mcp-plans/*.json` — CallMcpTool step definitions
- `artifacts/mcp-repair-bundles/proposals/*.json` — draft LocatorPatchResult

### 2. Run MCP repair in Cursor Agent

Open the prompt file for the failing/healed key, or ask:

> Repair `demo.green_button` using Playwright MCP per artifacts/mcp-repair-bundles/prompts/

The agent must:

1. Call MCP `browser_navigate` then `browser_snapshot`
2. Propose registry locators from live page (not guesses)
3. Write `artifacts/mcp-repair-bundles/resolved/<key>.json`

### 3. Apply reviewed patch

```bash
python -m healing.mcp_apply --key demo.green_button --apply
pytest tests/ -q
python -m healing.ci_gates
```

## Alternative: healing report suggestions

```bash
python -m healing.apply_suggestion --report artifacts/healing-reports/<test>.json --key <key> --change-type promote_fallback --apply
```

## Raw Playwright → smart auto-conversion

```bash
python -m healing.convert_to_smart --scan-tests --apply   # batch convert policy violations
pytest --healing-auto-convert                             # convert before run (dev)
```

## Raw Playwright learning mode (default)

Tests that use `page` only (no `smart` fixture) run as normal Playwright. The framework
records successful locator actions, writes registry drafts, and generates MCP repair bundles
for agent review — without blocking the test run.

```bash
pytest tests/test_pure_playwright_example.py -s
# artifacts/raw-learning/registry-drafts/<test>.yaml
# artifacts/raw-learning/reports/<test>.json
# artifacts/mcp-repair-bundles/prompts/auto_*__add_semantic_key.md
```

Environment:

- `HEALING_RAW_LEARNING=0` — disable passive recording
- `HEALING_RAW_MCP=0` — skip MCP bundle generation after raw runs
- `HEALING_REGISTRY_AUTO_APPLY=1` — merge new `auto.*` keys into `locator_registry.yaml`

Set `test_policy.raw_mode: error` in `healing/ci_gates_config.yaml` for strict smart-only CI.

## Phase C — Agent executor + approval + apply

```bash
# Full pipeline (internal_stub when no CURSOR_API_KEY)
bash scripts/run_agent_phase_c.sh

# Or step-by-step:
python -m healing.agent_runner --all
python -m healing.agent_executor --executor auto
python -m healing.approval_manifest init --overwrite
python -m healing.approval_manifest approve --key demo.green_button
python -m healing.agent_apply --apply
```

Cursor SDK executor: `export CURSOR_API_KEY=...` then `--executor cursor_sdk` or `EXECUTOR=cursor_sdk`.

Outputs:
- `artifacts/agent-proposals-resolved/*.json` — resolved + validation pass/fail
- `artifacts/agent-proposals-resolved/approval-manifest.json` — pending/approved/rejected per key

## CI

```bash
bash scripts/run_ci_gates.sh
```
