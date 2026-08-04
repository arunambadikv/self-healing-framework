# Agent Instructions — Playwright POM Healing Framework

**Project status:** [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — update when changing pipeline phases, architecture layout, or branch/CI policy.

## Architecture

- **Runtime root:** `healer-artifacts/` holds `healing.toml` + generated dirs (failures, queue, architecture, reports, auth); separate from the Python package `healing/`
- **Tests:** page-object fixtures (e.g. `orangehrm_login` in [`pages/orangehrm_login_page.py`](pages/orangehrm_login_page.py)); override app via `HEALING_BASE_URL`
- **Locators:** Python properties on page classes only (no `locator_registry.yaml` in runtime path)
- **Failures:** `healer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json` + `.md` + matching `screenshot-F-*.png` / `storage-state-F-*.json` (auto on pytest failure; `-2`/`-3` on same-second collision)
- **Patches:** `healer-artifacts/healing-queue/patches/P-{test-name}-{YYYYMMDD-HHMMSS}.json` (after MCP propose)
- **Manifest:** `healer-artifacts/architecture/manifest.json` (run scan before propose/review)
- **Queue statuses:** `pending_proposal` → `awaiting_agent` → `patch_ready` → `applied` | `skipped` | `deferred` | `not_healable`

## Slash skills

| Skill | Command |
|-------|---------|
| Bootstrap in a POM repo | `/healing-init` → `python -m healing.init` |
| Check consumer setup | `healing-doctor` (`--verify-mcp` optional) |
| Architecture scan | `/architecture-discovery` → `python -m healing.architecture_scan` (also auto on `healing-init` / pytest after package update) |
| Propose patches | `/healing-propose` → `python -m healing.pom_propose --process-all` |
| MCP propose (SDK) | `python -m healing.mcp_propose_runner --process-all` |
| Human review | `/healing-review` → `python -m healing.healing_review --list` |
| Locator repair (MCP + proposals) | `/playwright-locator-repair` |
| Human review + apply | `/healing-review` |
| Push to dev | `/push-to-dev` |

## Use in another framework

See **[docs/CONSUMER_SETUP.md](docs/CONSUMER_SETUP.md)** for full requirements, `healing-init` / `healing-doctor`, CLI reference, and troubleshooting.

```bash
pip install "healing[mcp] @ git+https://github.com/arunambadikv/self-healing-framework.git"
playwright install chromium
healing-init
cp .env.example .env   # set CURSOR_API_KEY for MCP propose only
healing-doctor
```

Skills ship inside the package (`healing/templates/skills/`) and `healing-init` installs them into `.cursor/skills/`. Runtime config/artifacts live under `healer-artifacts/` so they do not collide with the importable `healing` package. `.env` is auto-loaded for MCP propose. See README § Installation.

## Playwright MCP setup

```bash
healing-doctor --verify-mcp
# or: bash scripts/setup_mcp_agent.sh
```

- **CLI / CI propose:** `mcp_propose_runner` starts Playwright MCP via stdio from `.cursor/mcp.json` (or built-in defaults). No Cursor Settings click required.
- **Interactive IDE:** connect Playwright MCP in Cursor from `.cursor/mcp.json` if using slash skills with live browser tools.

For automated MCP propose:

```bash
source .venv/bin/activate
pip install -r requirements.txt   # includes cursor-sdk
# CURSOR_API_KEY in .env (loaded automatically)
```

## Failure → patch → apply workflow

### 1. Test fails (automatic)

```bash
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_login_button --run-healing-demo -v
# → healer-artifacts/failures/F-test_orangehrm_broken_login_button-20260801-123456.json + .md
# → classification: selector_break | network | app_regression | auth_failure | ...
# → non-healable failures marked not_healable in queue index
```

### 2. Refresh architecture context

```bash
python -m healing.architecture_scan
```

Or enable pre-test scan: `pytest --healing-scan-architecture tests/ -v`

### 3. Propose patches (stub → MCP complete)

**Manual steps:**

```bash
python -m healing.pom_propose --list
python -m healing.pom_propose --process-all
# → stub P-{test-name}-{stamp}.json (status: awaiting_agent) + P-…-agent-task.md

python -m healing.mcp_propose_runner --list
python -m healing.mcp_propose_runner --process-all
# → completes P-*.json via Cursor SDK + Playwright MCP (status: patch_ready)
```

**Single patch:**

```bash
python -m healing.mcp_propose_runner --patch-id P-<id>
```

**Auto chain after pytest** (opt-in; runs only when the session captured healable locator failures):

```bash
export HEALING_MCP_AUTO=1
export CURSOR_API_KEY=cursor_...
pytest tests/ -v
# on healable locator failure at session end → architecture_scan (if stale)
# → pom_propose (always new stub for this session's failures)
# → mcp_propose_runner (latest patch first; older duplicate architecture_ref skipped)
```

Agent task file per patch: `healer-artifacts/healing-queue/patches/P-<id>-agent-task.md`

Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to fill real `architecture_updates` in `P-*.json`. Then promote:

```bash
python -m healing.healing_review --promote P-<id>
```

Human apply is still required — do not edit `pages/*.py` during propose.

### 4. Human review (required before apply)

```bash
python -m healing.healing_review --list    # read-only table of patch_ready entries
python -m healing.healing_review --promote-all   # promote complete awaiting_agent patches
python -m healing.healing_review --interactive   # guided heal/skip/defer menu (default on TTY)
python -m healing.healing_review --promote P-<id>   # after skill-only MCP repair
python -m healing.healing_review --show P-<id>
python -m healing.healing_review --patch P-<id> --decision heal
python -m healing.healing_review --patch P-<id> --decision skip --reason "app regression"
python -m healing.healing_review --summary
```

Patches with TODO placeholders cannot be applied. Run `--promote` first if queue status is still `awaiting_agent`.

### 5. CI

GitHub Actions runs three jobs:

1. **test** — pytest + architecture scan + artifact upload
2. **propose-on-failure** — (on test failure) stub + `mcp_propose_runner` + review summary
3. **healing-gates** — full `python -m healing.ci_gates` after propose had a chance

Local equivalent:

```bash
pytest tests/ -q
python -m healing.architecture_scan
python -m healing.pom_propose --process-all
python -m healing.mcp_propose_runner --process-all
python -m healing.ci_gates
```

## Healing flow demos (opt-in)

Two intentional locator breaks for end-to-end pipeline testing. See [docs/HEALING_DEMO.md](docs/HEALING_DEMO.md).

```bash
pytest tests/test_orangehrm_healing.py --run-healing-demo -v
```

After `/healing-review` heal, reset intentional breaks before the next demo:

```bash
python scripts/reset_healing_demos.py
```

## Demo session test (deprecated)

Removed — use `tests/test_orangehrm_healing.py` with `--run-healing-demo` instead of `--run-demo-session`.

## Legacy

SmartPage + `locator_registry.yaml` are retired (removed from this repo). Locators live only on page-object properties.
