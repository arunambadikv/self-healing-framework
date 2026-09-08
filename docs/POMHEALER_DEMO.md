# Healing Flow Demo — Runbook

Four opt-in OrangeHRM tests plus Sauce Demo tests with **intentionally broken locators** to exercise the full pomhealer pipeline:

capture → classify → propose → MCP runner → human review → apply.

**Target app:** set via `POMHEALER_BASE_URL` (default: OrangeHRM demo login). The same flow works for any site using page-object tests.

Run only when explicitly requested (skipped in normal CI). Opens a **visible** browser with slow-mo by default; use `POMHEALER_DEMO_HEADLESS=1` for CI:

```bash
pytest tests/test_orangehrm_pomhealer.py --run-pomhealer-demo -v
```

Optional slow-mo (milliseconds):

```bash
POMHEALER_DEMO_SLOW_MO=800 pytest tests/test_orangehrm_pomhealer.py --run-pomhealer-demo -v
```

Pin Playwright browsers to a workspace folder so Cursor's sandbox does not re-download Chromium every session. In `.env`:

```bash
PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers
```

Then once (or after a Playwright upgrade):

```bash
playwright install chromium
```

If an agent still points at `/tmp/cursor-sandbox-cache/...`, pomhealer loads `.env` and prefers `.playwright-browsers/` over that ephemeral path. You can also unset a sandbox override in a normal terminal:

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
python -m pomhealer.architecture_scan
```

## Test case 1 — Broken login button locator

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_login_button` |
| Architecture ref | `OrangeHrmLoginPage.pomhealer_demo_login_button` |
| Broken | `get_by_role("button", name="Sign In")` |
| Expected fix | `get_by_role("button", name="Login")` |

```bash
export POMHEALER_MCP_AUTO=1
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button --run-pomhealer-demo -v
python -m pomhealer.review --promote-all   # if skill path left awaiting_agent
python -m pomhealer.review --list
python -m pomhealer.review --show P-<id>
python -m pomhealer.review --patch P-<id> --decision heal
```

## Test case 2 — Broken dashboard heading after login

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_post_login_broken_heading` |
| Architecture ref | `OrangeHrmDashboardPage.pomhealer_demo_dashboard_heading` |
| Broken | `get_by_role("heading", name="Home")` |
| Expected fix | `get_by_role("heading", name="Dashboard")` |

```bash
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_post_login_broken_heading --run-pomhealer-demo -v
```

## Test case 3 — Broken username field locator

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_username_field` |
| Architecture ref | `OrangeHrmLoginPage.pomhealer_demo_username_input` |
| Broken | `get_by_role("textbox", name="User Name")` |
| Expected fix | `get_by_role("textbox", name="Username")` |

```bash
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_username_field --run-pomhealer-demo -v
```

## Test case 4 — Broken PIM menu link after login

| Field | Value |
|-------|-------|
| Test | `test_orangehrm_broken_pim_menu` |
| Architecture ref | `OrangeHrmDashboardPage.pomhealer_demo_pim_link` |
| Broken | `get_by_role("link", name="Employee List")` |
| Expected fix | `get_by_role("link", name="PIM")` |

```bash
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_pim_menu --run-pomhealer-demo -v
```

Run **one test at a time** to keep the pomhealer queue easy to review.

## Test case 5 — Sauce Demo broken login button

| Field | Value |
|-------|-------|
| Test | `test_saucedemo_broken_login_button` |
| Architecture ref | `SauceDemoLoginPage.pomhealer_demo_login_button` |
| Broken | `get_by_role("button", name="Sign In")` |
| Expected fix | `get_by_role("button", name="Login")` |
| Site | https://www.saucedemo.com/ (`standard_user` / `secret_sauce`) |

```bash
export POMHEALER_MCP_AUTO=1
pytest tests/test_saucedemo_pomhealer.py::test_saucedemo_broken_login_button --run-pomhealer-demo -v
python -m pomhealer.review --list
python -m pomhealer.review --patch P-<id> --decision heal --yes
```

## Test case 6 — Sauce Demo inventory (authenticated multi-page)

| Field | Value |
|-------|-------|
| Test | `test_saucedemo_broken_inventory_add_to_cart` |
| Architecture ref | `SauceDemoInventoryPage.pomhealer_demo_add_backpack` |
| Broken | `get_by_role("button", name="Add Backpack")` |
| Expected fix | `get_by_role("button", name="Add to cart").first` (or product-specific name) |

```bash
pytest tests/test_saucedemo_pomhealer.py::test_saucedemo_broken_inventory_add_to_cart --run-pomhealer-demo -v
```

Storage-state variant (login once via fixture):

```bash
pytest tests/test_saucedemo_pomhealer.py::test_saucedemo_broken_inventory_with_storage_state --run-pomhealer-demo -v
```

## Auth / credentials

Public demo defaults work out of the box. Override via env (never commit secrets):

```bash
export ORANGEHRM_USER=Admin
export ORANGEHRM_PASSWORD=admin123
export SAUCEDEMO_USER=standard_user
export SAUCEDEMO_PASSWORD=secret_sauce
```

Session fixtures write `pomhealer-artifacts/auth/storage-state-*.json` for reuse and MCP `--storage-state`.

Session expiry / redirect-to-login is classified as `auth_failure` (`not_healable`) — do not propose locator patches for expired sessions.

## Headless CI / remote GitHub Actions

```bash
export POMHEALER_DEMO_HEADLESS=1
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button --run-pomhealer-demo -v
```

Remote pipeline (needs `CURSOR_API_KEY` secret for MCP step):

```bash
gh workflow run pomhealer-pipeline-e2e.yml -f scenario=login_button
gh run watch
# scenarios: login_button | authenticated_dashboard | saucedemo_inventory
```

Daily architecture heartbeat: see [ARCHITECTURE_HEARTBEAT.md](ARCHITECTURE_HEARTBEAT.md).

## After human heal — reset demo locators

Healing review applies fixes to `pages/*.py`. Re-break demo locators before the next pipeline run:

```bash
python scripts/reset_pomhealer_demos.py
```

## Auto chain (optional)

Runs at session end **only when** a healable locator failure (`selector_break`) was captured in that run. Requires `CURSOR_API_KEY` for the MCP step.

```bash
export POMHEALER_MCP_AUTO=1
export CURSOR_API_KEY=cursor_...
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button --run-pomhealer-demo -v
python -m pomhealer.review --promote-all
python -m pomhealer.review --list
python -m pomhealer.review --patch P-<id> --decision heal
```

## Expected artifacts

| Stage | Artifact / status |
|-------|-------------------|
| Fail | `pomhealer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json`, `.md`, `screenshot-F-….png`, `storage-state-F-….json` |
| Capture | `classification: selector_break`, queue `pending_proposal` |
| Stub propose | `P-{test-name}-{stamp}.json`, `P-…-agent-task.md`, queue `awaiting_agent` |
| MCP complete | MCP loads `storage_state` (or replays steps) → `page_url` → snapshot → real `after`, queue `patch_ready` |
| Human heal | `pages/*.py` updated, queue `applied`; `P-*` files leave pending `patches/` → `applied/` |

## Verify normal CI stays green

```bash
pytest tests/ -q
# pomhealer_demo tests should show as skipped
```
