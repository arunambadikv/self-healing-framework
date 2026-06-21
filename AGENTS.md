# Agent Instructions — Playwright POM Healing Framework

**Project status:** [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — update when changing pipeline phases, architecture layout, or branch/CI policy.

## Architecture

- **Tests:** raw Playwright via `demo` fixture (`DemoPage` in [`pages/demo_page.py`](pages/demo_page.py))
- **Locators:** Python properties on page classes only (no `locator_registry.yaml` in runtime path)
- **Failures:** `artifacts/failures/F-*.json` + `.md` (auto on pytest failure)
- **Patches:** `artifacts/healing-queue/patches/P-*.json` (after MCP propose)
- **Manifest:** `artifacts/architecture/manifest.json` (run scan before propose/review)
- **Queue statuses:** `pending_proposal` → `awaiting_agent` → `patch_ready` → `applied` | `skipped` | `not_healable`

## Slash skills

| Skill | Command |
|-------|---------|
| Architecture scan | `/architecture-discovery` → `python -m healing.architecture_scan` |
| Propose patches | `/healing-propose` → `python -m healing.pom_propose --process-all` |
| MCP propose (SDK) | `python -m healing.mcp_propose_runner --process-all` |
| Human review | `/healing-review` → `python -m healing.healing_review --list` |
| Locator repair (MCP + proposals) | `/playwright-locator-repair` |
| Human review + apply | `/healing-review` |
| Push to dev | `/push-to-dev` |

## Playwright MCP setup

```bash
bash scripts/setup_mcp_agent.sh
```

Connect Playwright MCP in Cursor (`.cursor/mcp.json`). Skills live in `.cursor/skills/`.

For automated MCP propose, install deps in the project venv and set `CURSOR_API_KEY`:

```bash
source .venv/bin/activate
pip install -r requirements.txt   # includes cursor-sdk
export CURSOR_API_KEY=cursor_...
```

## Failure → patch → apply workflow

### 1. Test fails (automatic)

```bash
pytest tests/test_demo_buttons_links.py -v
# → artifacts/failures/F-<id>.json + .md
# → classification: selector_break | network | app_regression | ...
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
# → stub P-*.json (status: awaiting_agent) + P-<id>-agent-task.md

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
# on healable locator failure at session end → architecture_scan (if stale) → pom_propose → mcp_propose_runner
```

Agent task file per patch: `artifacts/healing-queue/patches/P-<id>-agent-task.md`

Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to fill real `architecture_updates` in `P-*.json`. Then promote:

```bash
python -m healing.healing_review --promote P-<id>
```

Human apply is still required — do not edit `pages/*.py` during propose.

### 4. Human review (required before apply)

```bash
python -m healing.healing_review --list    # table view; auto-promotes complete awaiting_agent patches
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
pytest tests/test_healing_flow_demo.py --run-healing-demo -v
```

## Demo session test (deprecated)

Replaced by `tests/test_healing_flow_demo.py` — use `--run-healing-demo` instead of `--run-demo-session`.

## Legacy

SmartPage + `locator_registry.yaml` moved to [`legacy/`](legacy/) for reference only.
