# Healing Flow Demo — Runbook

Four opt-in tests with **intentionally broken locators** to exercise the full healing pipeline:

capture → classify → propose → MCP runner → human review → apply.

**Target app:** set via `HEALING_BASE_URL` (default: OrangeHRM demo login). The same flow works for any site using page-object tests.

Run only when explicitly requested (skipped in normal CI). **Opens a visible browser** with slow-mo:

```bash
pytest tests/test_orangehrm_healing.py --run-healing-demo -v
```

Optional slow-mo (milliseconds):

```bash
HEALING_DEMO_SLOW_MO=800 pytest tests/test_orangehrm_healing.py --run-healing-demo -v
```

Unset `PLAYWRIGHT_BROWSERS_PATH` if Cursor sandbox pointed Playwright at a temp cache:

```bash
unset PLAYWRIGHT_BROWSERS_PATH
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

## Test case 1 — Broken login button locator

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_login_button` |
| Architecture ref | `OrangeHrmLoginPage.healing_demo_login_button` |
| Broken | `get_by_role("button", name="Sign In")` |
| Expected fix | `get_by_role("button", name="Login")` |

```bash
export HEALING_MCP_AUTO=1
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_login_button --run-healing-demo -v
python -m healing.healing_review --promote-all   # if skill path left awaiting_agent
python -m healing.healing_review --list
python -m healing.healing_review --show P-<id>
python -m healing.healing_review --patch P-<id> --decision heal
```

## Test case 2 — Broken dashboard heading after login

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_post_login_broken_heading` |
| Architecture ref | `OrangeHrmDashboardPage.healing_demo_dashboard_heading` |
| Broken | `get_by_role("heading", name="Home")` |
| Expected fix | `get_by_role("heading", name="Dashboard")` |

```bash
pytest tests/test_orangehrm_healing.py::test_orangehrm_post_login_broken_heading --run-healing-demo -v
```

## Test case 3 — Broken username field locator

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_username_field` |
| Architecture ref | `OrangeHrmLoginPage.healing_demo_username_input` |
| Broken | `get_by_role("textbox", name="User Name")` |
| Expected fix | `get_by_role("textbox", name="Username")` |

```bash
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_username_field --run-healing-demo -v
```

## Test case 4 — Broken PIM menu link after login

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_pim_menu` |
| Architecture ref | `OrangeHrmDashboardPage.healing_demo_pim_link` |
| Broken | `get_by_role("link", name="Employee List")` |
| Expected fix | `get_by_role("link", name="PIM")` |

```bash
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_pim_menu --run-healing-demo -v
```

Run **one test at a time** to keep the healing queue easy to review.

## After human heal — reset demo locators

Healing review applies fixes to `pages/*.py`. Re-break demo locators before the next pipeline run:

```bash
python scripts/reset_healing_demos.py
```

## Auto chain (optional)

Runs at session end **only when** a healable locator failure (`selector_break`) was captured in that run. Requires `CURSOR_API_KEY` for the MCP step.

```bash
export HEALING_MCP_AUTO=1
export CURSOR_API_KEY=cursor_...
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_login_button --run-healing-demo -v
python -m healing.healing_review --promote-all
python -m healing.healing_review --list
python -m healing.healing_review --patch P-<id> --decision heal
```

## Expected artifacts

| Stage | Artifact / status |
|-------|-------------------|
| Fail | `artifacts/failures/F-*.json`, `.md`, screenshot, `storage-state-F-*.json` |
| Capture | `classification: selector_break`, queue `pending_proposal` |
| Stub propose | `P-*.json`, `P-*-agent-task.md`, queue `awaiting_agent` |
| MCP complete | MCP loads `storage_state` (or replays steps) → `page_url` → snapshot → real `after`, queue `patch_ready` |
| Human heal | `pages/*.py` updated, queue `applied` |

## Verify normal CI stays green

```bash
pytest tests/ -q
# healing_demo tests should show as skipped
```
