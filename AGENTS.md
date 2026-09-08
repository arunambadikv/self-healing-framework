# Agent Instructions — Playwright POM pomhealer Framework

**Project status:** [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — update when changing pipeline phases, architecture layout, or branch/CI policy.

## Architecture

- **Runtime root:** `pomhealer-artifacts/` holds `pomhealer.toml` + generated dirs (failures, queue, architecture, reports, auth); separate from the Python package `pomhealer/`
- **Tests:** page-object fixtures (e.g. `orangehrm_login` in [`pages/orangehrm_login_page.py`](pages/orangehrm_login_page.py)); override app via `POMHEALER_BASE_URL`
- **Locators:** Python properties on page classes only (no `locator_registry.yaml` in runtime path)
- **Failures:** `pomhealer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json` + `.md` + matching `screenshot-F-*.png` / `storage-state-F-*.json` (auto on pytest failure; `-2`/`-3` on same-second collision)
- **Patches (pending):** `pomhealer-artifacts/pomhealer-queue/patches/P-{test-name}-{YYYYMMDD-HHMMSS}.json` (+ `.md` / `-agent-task.md`) while awaiting propose/review
- **Patches (done):** heal/skip moves those files to `pomhealer-queue/applied/` or `skipped/` (pending `patches/` stays empty of finished work)
- **Manifest:** `pomhealer-artifacts/architecture/manifest.json` (run scan before propose/review)
- **Queue statuses:** `pending_proposal` → `awaiting_agent` → `patch_ready` → `applied` | `skipped` | `deferred` | `not_healable`

## Slash skills

| Skill | Command |
|-------|---------|
| Bootstrap in a POM repo | `/pomhealer-init` → `python -m pomhealer.init` |
| Check consumer setup | `pomhealer-doctor` (`--verify-mcp` optional) |
| Architecture scan | `/architecture-discovery` → `python -m pomhealer.architecture_scan` (also auto on `pomhealer-init` / pytest after package update; skills + `.env.example` refresh the same way) |
| Propose patches | `/pomhealer-propose` → `python -m pomhealer.pom_propose --process-all` |
| MCP propose (SDK) | `python -m pomhealer.mcp_propose_runner --process-all` |
| Human review | `/pomhealer-review` → `python -m pomhealer.review --list` (auto-imports CI downloads) |
| Import CI artifacts | `pomhealer-import` (`python -m pomhealer.artifact_import`) |
| Locator repair (MCP + proposals) | `/playwright-locator-repair` |
| Human review + apply | `/pomhealer-review` |
| Push to dev | `/push-to-dev` |

## Use in another framework

See **[docs/CONSUMER_SETUP.md](docs/CONSUMER_SETUP.md)** for full requirements, `pomhealer-init` / `pomhealer-doctor`, CLI reference, and troubleshooting.

```bash
pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
playwright install chromium
pomhealer-init
cp .env.example .env   # set POMHEALER_LLM_PROVIDER + matching API key for MCP propose only
pomhealer-doctor
```

Skills ship inside the package (`pomhealer/templates/skills/`) and `pomhealer-init` installs them into `.cursor/skills/`. After `pip install -U` from git, the next pytest / pomhealer-doctor / pomhealer-review refreshes those bundled skills and `.env.example` automatically (`.env` is never overwritten).

## Playwright MCP setup

```bash
pomhealer-doctor --verify-mcp
# or: bash scripts/setup_mcp_agent.sh
```

- **CLI / CI propose:** `mcp_propose_runner` starts Playwright MCP via stdio from `.cursor/mcp.json` (or built-in defaults). No Cursor Settings click required.
- **Interactive IDE:** connect Playwright MCP in Cursor from `.cursor/mcp.json` if using slash skills with live browser tools.

For automated MCP propose:

```bash
source .venv/bin/activate
pip install -r requirements.txt   # includes cursor-sdk, openai, mcp
# POMHEALER_LLM_PROVIDER + matching API key in .env (loaded automatically)
```

## Failure → patch → apply workflow

### 1. Test fails (automatic)

```bash
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button --run-pomhealer-demo -v
# → pomhealer-artifacts/failures/F-test_orangehrm_broken_login_button-20260801-123456.json + .md
# → classification: selector_break | network | app_regression | auth_failure | ...
# → only selector_break is healable; others marked not_healable in queue index
```

### 2. Refresh architecture context

```bash
python -m pomhealer.architecture_scan
```

Or enable pre-test scan: `pytest --pomhealer-scan-architecture tests/ -v`

### 3. Propose patches (stub → MCP complete)

**Manual steps:**

```bash
python -m pomhealer.pom_propose --list
python -m pomhealer.pom_propose --process-all
# → stub P-{test-name}-{stamp}.json (status: awaiting_agent) + P-…-agent-task.md

python -m pomhealer.mcp_propose_runner --list
python -m pomhealer.mcp_propose_runner --process-all
# → completes P-*.json via LLM provider + Playwright MCP (status: patch_ready)
#    cursor: Cursor SDK; openai/gemini/groq/litellm: OpenAI-compatible Chat Completions
#    defaults: composer-2.5 / gpt-4.1 / gemini-3.6-flash / openai/gpt-oss-120b / gpt-4o-mini
```

**Single patch:**

```bash
python -m pomhealer.mcp_propose_runner --patch-id P-<id>
```

**Auto chain after pytest** (opt-in; runs only when the session captured healable locator failures):

```bash
export POMHEALER_MCP_AUTO=1
# POMHEALER_LLM_PROVIDER=cursor|openai|gemini|groq|litellm + matching key in .env
pytest tests/ -v
# on healable locator failure at session end → architecture_scan (if stale)
# → pom_propose (always new stub for this session's failures)
# → mcp_propose_runner (latest patch first; older duplicate architecture_ref skipped)
```

Agent task file per in-flight patch: `pomhealer-artifacts/pomhealer-queue/patches/P-<id>-agent-task.md`.
After heal/skip it moves to `applied/` or `skipped/` with the json/md — do not leave related files in pending `patches/`.

Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to fill real `architecture_updates` in `P-*.json`. Then promote:

```bash
python -m pomhealer.review --promote P-<id>
```

Human apply is still required — do not edit `pages/*.py` during propose.

### 4. Human review (required before apply)

```bash
python -m pomhealer.review --list    # read-only table of patch_ready entries
python -m pomhealer.review --promote-all   # promote complete awaiting_agent patches
python -m pomhealer.review --interactive   # guided heal/skip/defer menu (default on TTY)
python -m pomhealer.review --promote P-<id>   # after skill-only MCP repair
python -m pomhealer.review --show P-<id>
python -m pomhealer.review --patch P-<id> --decision heal
python -m pomhealer.review --patch P-<id> --decision skip --reason "app regression"
python -m pomhealer.review --summary
```

Patches with TODO placeholders cannot be applied. Run `--promote` first if queue status is still `awaiting_agent`.

### 5. CI

GitHub Actions runs three jobs:

1. **test** — pytest + architecture scan + artifact upload
2. **propose-on-failure** — (on test failure) stub + `mcp_propose_runner` + review summary
3. **pomhealer-gates** — full `python -m pomhealer.ci_gates` after propose had a chance

Local equivalent:

```bash
pytest tests/ -q
python -m pomhealer.architecture_scan
python -m pomhealer.pom_propose --process-all
python -m pomhealer.mcp_propose_runner --process-all
python -m pomhealer.ci_gates
```

## Healing flow demos (opt-in)

Two intentional locator breaks for end-to-end pipeline testing. See [docs/POMHEALER_DEMO.md](docs/POMHEALER_DEMO.md).

```bash
pytest tests/test_orangehrm_pomhealer.py --run-pomhealer-demo -v
```

After `/pomhealer-review` heal, reset intentional breaks before the next demo:

```bash
python scripts/reset_pomhealer_demos.py
```

## Demo session test (deprecated)

Removed — use `tests/test_orangehrm_pomhealer.py` with `--run-pomhealer-demo` instead of `--run-demo-session`.

## Legacy

SmartPage + `locator_registry.yaml` are retired (removed from this repo). Locators live only on page-object properties.
