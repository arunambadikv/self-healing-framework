# Healing Flow Demo — Runbook

Two opt-in tests with **intentionally broken locators** to exercise the full healing pipeline:

capture → classify → propose → MCP runner → human review → apply.

Run only when explicitly requested (skipped in normal CI):

```bash
pytest tests/test_healing_flow_demo.py --run-healing-demo -v
```

## Prerequisites

```bash
cd /path/to/playwright-healing-framework
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
set -a && source .env && set +a   # CURSOR_API_KEY for mcp_propose_runner
python -m healing.architecture_scan
```

## Test case 1 — Broken link locator

| Field | Value |
|-------|-------|
| Test | `test_healing_demo_github_link` |
| Architecture ref | `DemoPage.session_github_link` |
| Broken | `get_by_role("link", name="WRONG_GITHUB_LINK_DEMO")` |
| Expected fix | `get_by_role("link", name="SeleniumBase on GitHub")` |

```bash
pytest tests/test_healing_flow_demo.py::test_healing_demo_github_link --run-healing-demo -v
python -m healing.pom_propose --process-all
python -m healing.mcp_propose_runner --process-all
python -m healing.healing_review --list
python -m healing.healing_review --show P-<id>
python -m healing.healing_review --patch P-<id> --decision heal
pytest tests/test_healing_flow_demo.py::test_healing_demo_github_link --run-healing-demo -v
```

## Test case 2 — Broken button locator

| Field | Value |
|-------|-------|
| Test | `test_healing_demo_green_button` |
| Architecture ref | `DemoPage.healing_demo_green_button` |
| Broken | `get_by_role("button", name="Click Me (Blue)")` |
| Expected fix | `get_by_role("button", name="Click Me (Green)")` |

```bash
pytest tests/test_healing_flow_demo.py::test_healing_demo_green_button --run-healing-demo -v
python -m healing.pom_propose --process-all
python -m healing.mcp_propose_runner --process-all
python -m healing.healing_review --list
python -m healing.healing_review --show P-<id>
python -m healing.healing_review --patch P-<id> --decision heal
pytest tests/test_healing_flow_demo.py::test_healing_demo_green_button --run-healing-demo -v
```

Run **one test at a time** to keep the healing queue easy to review.

## Auto chain (optional)

Runs at session end **only when** a healable locator failure (`selector_break`) was captured in that run. Requires `CURSOR_API_KEY` for the MCP step.

```bash
export HEALING_MCP_AUTO=1
export CURSOR_API_KEY=cursor_...
pytest tests/test_healing_flow_demo.py::test_healing_demo_github_link --run-healing-demo -v
python -m healing.healing_review --list
python -m healing.healing_review --patch P-<id> --decision heal
```

## Expected artifacts

| Stage | Artifact / status |
|-------|-------------------|
| Fail | `artifacts/failures/F-*.json`, `.md`, screenshot |
| Capture | `classification: selector_break`, queue `pending_proposal` |
| Stub propose | `P-*.json`, `P-*-agent-task.md`, queue `awaiting_agent` |
| MCP complete | `P-*.json` with real `after`, queue `patch_ready` |
| Human heal | `pages/demo_page.py` updated, queue `applied` |

## Verify normal CI stays green

```bash
pytest tests/ -q
# healing_demo tests should show as skipped
```
