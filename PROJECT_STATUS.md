# Playwright Self-Healing Framework — Project Status

**Validation target:** [SeleniumBase demo page](https://seleniumbase.io/demo_page)  
**Stack:** Playwright Python, pytest, YAML locator registry, deterministic runtime healing

---

## 1. What's Completed

### Core Framework

| Area | Status |
|------|--------|
| Semantic-key tests via `SmartPage` | Done |
| `locator_registry.yaml` (preferred + fallback per key) | Done — 30+ demo keys |
| Locator builder (`test_id`, `role`, `label`, `text`, `placeholder`, `css`, `frame_css`) | Done |
| Deterministic healing (preferred → fallback) | Done |
| JSON healing reports per test | Done — `artifacts/healing-reports/` |
| Markdown patch suggestions | Done — `artifacts/patch-suggestions/` |
| Intentional healing demo (`demo.green_button` broken preferred) | Done |
| Demo test suite (inputs, buttons/links, dropdowns, radios/checkboxes, iframe, slider/progress) | Done — 8+ test files |
| Skills (repair, registry-update, patching) | Done — `skills/` |
| README + install/run docs | Done |

### Safety & Quality (Pre-AI Hardening)

| Feature | Status |
|---------|--------|
| Action contract enforcement (`smart.fill` vs registry `action`) | Done |
| Registry validation on load + `python -m healing.registry_lint` | Done |
| Structured failure diagnostics (per-candidate errors) | Done |
| Missing-key detection + stub suggestions in reports | Done |
| Review-only registry apply CLI | Done — `python -m healing.apply_suggestion ... --apply` |
| Agent runner (prompt bundles + proposals, no auto-write) | Done — `python -m healing.agent_runner` |
| Raw → smart converter (dry-run / `--apply`) | Done — `python -m healing.convert_to_smart` |

### Operational Notes

- Registry updates are **manual or explicit CLI** after review — not silent CI mutation.
- Playwright MCP was used for **page inspection** when building/refining locators; it is **not** wired into automatic runtime suggestion generation today.
- Full suite verified green with one optional skip (drag/drop on public demo).

---

## 2. Advantages

1. **Tests stay readable** — `smart.click("demo.green_button")` expresses intent; selectors live in one registry.
2. **Deterministic resilience** — Same key always tries the same candidate order; no mid-test LLM calls.
3. **Observable health** — Reports show `primary` / `healed` / `failed` per action; repeated healing signals locator drift.
4. **Controlled maintenance** — Patch suggestions + optional `apply_suggestion` keep changes reviewable and auditable.
5. **Reusable beyond demo** — Copy `healing/`, registry pattern, and skills to any app with a new `locator_registry.yaml`.
6. **Safe by design** — No assertion weakening, no silent test rewrites during normal runs.
7. **Onboarding path for legacy tests** — Converter can migrate common raw Playwright lines to semantic keys where registry mapping exists.

---

## 3. Limitations (Current)

| Limitation | Impact |
|------------|--------|
| No auto-discovery of locators at runtime | Missing keys fail fast with TODO stubs; real locators must be added (MCP/agent/manual). |
| Demo page has no `data-testid` | Many entries rely on CSS/role; label-based locators often don't work on table layout. |
| Suggestions for missing keys are rule-based stubs | Not AI-refined unless you run a separate agent/MCP workflow. |
| `agent_runner` generates prompts/proposals only | Does not call Cursor/API or apply patches by itself. |
| Converter covers common patterns only | Complex flows, chains, drag/drop, custom `evaluate` need manual conversion. |
| Healing can mask drift if ignored | High `healed` ratio without registry updates = technical debt. |
| Drag/drop on public demo | Flaky; test skipped/optional. |
| Non-smart tests bypass healing | Raw `page.locator` tests get empty reports unless converted. |

---

## 4. Architecture

```text
Test (smart.* semantic key)
    → locator_registry.yaml (preferred → fallback)
    → SmartPage + locator_builder → Playwright
    → success: record primary/healed
    → failure: structured error + report

Post-run (optional):
    → patch suggestions (Markdown)
    → agent_runner → agent prompts + proposal JSON
    → human review → apply_suggestion --apply
```

**Not in runtime path today:** Playwright MCP, autonomous agent writes to registry/tests.

---

## 5. MCP + Agents Roadmap

### Phase A — Observation & Gates ✅ Implemented

- `python -m healing.registry_lint` — registry schema validation + lint warnings
- `python -m healing.ci_gates` — healing thresholds + smart test policy
- Config: `healing/ci_gates_config.yaml` (failed events, healed ratio warn/fail, allowlist)
- `healing/test_policy.py` — blocks raw `page.locator` / `page.get_by_*` in tests (allowlist supported)
- GitHub Actions: `.github/workflows/healing-ci.yml`
- Helper script: `scripts/run_ci_gates.sh`

### Phase B — MCP-Assisted Locator Authoring ✅ Implemented (Cursor MCP)

- `.cursor/mcp.json` — Playwright MCP server reference for Cursor
- `.cursor/rules/playwright-mcp-repair.mdc` — agent rule for MCP repair tasks
- `AGENTS.md` — end-to-end MCP repair instructions
- `healing/mcp_tools.py` — CallMcpTool step definitions (`browser_navigate`, `browser_snapshot`)
- `healing/mcp_apply.py` — apply agent-written `resolved/<key>.json` to registry
- `python -m healing.mcp_repair_pipeline` — prompts + mcp-plans + proposals
- `bash scripts/repair_with_mcp.sh` — pytest + gates + bundles + instructions
- `HEALING_TRIGGER_MCP_REPAIR=1 pytest` — auto-bundle on healed/failed tests
- Human applies: `python -m healing.mcp_apply --key <key> --apply`

### Phase C — Wire Agent Execution to `agent_runner` ✅

- `python -m healing.agent_executor` — consumes `artifacts/agent-prompts/*.md`, writes `artifacts/agent-proposals-resolved/`
- Executors: `internal_stub` (draft proposals) or `cursor_sdk` (`CURSOR_API_KEY` + `cursor-sdk`)
- Validates each proposal via patched temp registry + `validation_command`
- `python -m healing.approval_manifest` — approve/reject per key before apply
- `python -m healing.agent_apply --apply` — apply **approved** entries only
- `bash scripts/run_agent_phase_c.sh` — full Phase C pipeline

### Phase D — Optional Dev-Only Auto-Apply (Strict)

- Only `LOCAL_DEV`, only low-risk actions (`expect_visible`, `fill`)
- Never auto-apply destructive/payment/permission actions
- Confidence threshold + registry validation + targeted pytest rerun

### What We Still Need for Full Agent Loop

| Item | Purpose |
|------|---------|
| Agent executor integration | Turn prompt files into real patch JSON |
| MCP in repair pipeline | Replace TODO stubs with inspected locators |
| Approval workflow | Explicit approve before `--apply` |
| Proposal ingestion | Parse agent JSON → merge with proposals |
| Metrics | Per-key heal frequency, promotion recommendations |

---

## 6. Quick Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium

# Run tests
pytest
pytest tests/test_demo_buttons_links.py --headed

# Phase A — CI gates
python -m healing.registry_lint
python -m healing.ci_gates
bash scripts/run_ci_gates.sh

# Phase B — MCP repair bundles
python -m healing.mcp_repair_pipeline
python -m healing.mcp_repair_pipeline --inspect
INSPECT=1 bash scripts/run_mcp_repair.sh

# Post-run suggestions (legacy agent runner)
python -m healing.agent_runner          # new reports only
python -m healing.agent_runner --all    # all reports

# Apply reviewed change
python -m healing.apply_suggestion \
  --report artifacts/healing-reports/test_buttons_links[chromium].json \
  --key demo.green_button \
  --change-type promote_fallback \
  --apply

# Migrate raw test
python -m healing.convert_to_smart --file tests/test_demo_non_smart.py --apply
```

**MCP (inspection only, manual):** `npx @playwright/mcp@latest`

---

## 7. Summary

We have a **production-oriented, deterministic self-healing test layer** with registry-driven locators, healing telemetry, and reviewable patch workflows. **AI/MCP is positioned as an assisted repair lane**, not silent CI mutation — the next investment is connecting `agent_runner` to an executor + MCP inspection + approval gates.
