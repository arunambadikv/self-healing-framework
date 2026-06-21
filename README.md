# Playwright Python POM Healing Framework

Page Object Model tests (`pages/*.py`) with **fail-fast** execution and a **post-failure healing pipeline**: capture failures → MCP/agent patch proposals → human review → apply locator fixes in page objects only.

**Demo app:** [SeleniumBase demo page](https://seleniumbase.io/demo_page)

**Operator guide:** [AGENTS.md](AGENTS.md)  
**Project status:** [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -m healing.architecture_scan
```

For automated MCP propose (Phase C), set `CURSOR_API_KEY` in `.env` (see `.env.example`). The `cursor-sdk` package is included in `requirements.txt`.

## Quick start

```python
def test_example(demo):
    demo.goto()
    demo.click_green_button()
    demo.expect_green_text_visible()
```

## Healing workflow

```bash
pytest tests/ -v
# on failure → artifacts/failures/F-*.json + .md

python -m healing.architecture_scan
python -m healing.pom_propose --process-all
python -m healing.mcp_propose_runner --process-all   # needs CURSOR_API_KEY + venv
# or opt-in auto chain after healable locator failures: HEALING_MCP_AUTO=1 pytest tests/ -v

python -m healing.healing_review --list
python -m healing.healing_review --patch P-<id> --decision heal
python -m healing.healing_review --summary
```

## Slash skills (Cursor)

| Command | Purpose |
|---------|---------|
| `/architecture-discovery` | Refresh `artifacts/architecture/manifest.json` |
| `/healing-propose` | Create patch proposals from failures |
| `/playwright-locator-repair` | MCP diagnosis + write `P-*.json` proposals |
| `/healing-review` | Human approve / skip / apply via `pom_apply` |

## CI

GitHub Actions runs **test** → **propose-on-failure** (on failure) → **healing-gates** (full queue checks after propose).

Local:

```bash
pytest tests/ -q
python -m healing.architecture_scan
python -m healing.ci_gates
# or
bash scripts/run_ci_gates.sh
```

## Branch policy

Repository: [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

- **`dev`** — integration and healing work
- **`main`** — PR + green **Healing Framework CI** (`test` + `healing-gates`)

See [AGENTS.md](AGENTS.md) and GitHub branch protection for `main`.

## Layout

```text
pages/              # locators + methods (single source of truth)
tests/              # tests use `demo` fixture only
healing/            # failure capture, queue, pom_apply, architecture_scan
.cursor/skills/      # slash-command skills
artifacts/          # generated (gitignored): failures/, healing-queue/, architecture/
demo-assets/        # example MCP resolved JSON
```

## Healing flow demos (opt-in)

Two intentional locator breaks to exercise the full pipeline. See [docs/HEALING_DEMO.md](docs/HEALING_DEMO.md).

```bash
pytest tests/test_healing_flow_demo.py --run-healing-demo -v
# opens a visible browser (slow-mo 400ms; set HEALING_DEMO_SLOW_MO to change)
```

## Demo session test (deprecated)

Use [docs/HEALING_DEMO.md](docs/HEALING_DEMO.md) instead:

```bash
pytest tests/test_healing_flow_demo.py --run-healing-demo -v
```
