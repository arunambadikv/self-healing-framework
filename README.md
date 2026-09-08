# Playwright Python POM — pomhealer

Page Object Model tests (`pages/*.py`) with **fail-fast** execution and a **post-failure pomhealer pipeline**: capture failures → MCP/agent patch proposals → human review → apply locator fixes in page objects only.

**Demo app:** [SeleniumBase demo page](https://seleniumbase.io/demo_page)

**Consumer setup (install, init, doctor, requirements):** [docs/CONSUMER_SETUP.md](docs/CONSUMER_SETUP.md)  
**Operator guide:** [AGENTS.md](AGENTS.md)  
**Project status:** [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)  
**QA Chapters / Confluence pack:** [docs/CONFLUENCE_QA_CHAPTERS.md](docs/CONFLUENCE_QA_CHAPTERS.md) (+ [docs/attachments/](docs/attachments/))

## Installation

Full consumer steps, CLI reference, and troubleshooting: **[docs/CONSUMER_SETUP.md](docs/CONSUMER_SETUP.md)**.

### Consumer happy path (another Playwright POM repo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
# or local: pip install -e "/path/to/self-healing-framework"
playwright install chromium
cd /path/to/your-pom-project
pomhealer-init                 # config, artifacts, skills, .cursor/mcp.json, .env.example + doctor
cp .env.example .env         # set POMHEALER_LLM_PROVIDER + matching API key for MCP propose
# defaults: composer-2.5 / gpt-4.1 / gemini-3.6-flash / openai/gpt-oss-120b
pomhealer-doctor               # re-check anytime; add --verify-mcp to probe npx Playwright MCP
pytest tests/ -v
# optional auto propose: set POMHEALER_MCP_AUTO=1 in .env (loaded automatically)
```

`pomhealer-init` writes `pomhealer-artifacts/pomhealer.toml`, artifact dirs, Cursor skills into `.cursor/skills/`, a Playwright MCP stub, and `.env.example`. Skills also ship inside the package when `.cursor/skills/` is absent. Pytest loads the plugin via the `pytest11` entry point.

**What needs a secret / MCP**

| Capability | Needs |
|------------|--------|
| Capture, scan, stub propose, review, apply | Nothing beyond pip + chromium |
| Automated MCP propose (`mcp_propose_runner` / `POMHEALER_MCP_AUTO`) | `POMHEALER_LLM_PROVIDER` + matching key in `.env`, Node/`npx` (`cursor`/`openai`/`gemini`/`groq`/`litellm`) |
| CI propose-on-failure | Same secrets as repo variables — see [docs/CONSUMER_CI.md](docs/CONSUMER_CI.md) |
| Interactive Cursor slash repair | Enable Playwright MCP from `.cursor/mcp.json` in Cursor Settings (IDE only — CLI propose starts MCP via stdio itself) |

### This reference repo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
playwright install chromium
python -m pomhealer.architecture_scan
pomhealer-doctor
```

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
# on failure → pomhealer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json + .md

python -m pomhealer.architecture_scan
python -m pomhealer.pom_propose --process-all
python -m pomhealer.mcp_propose_runner --process-all   # needs POMHEALER_LLM_PROVIDER + key + venv
# or opt-in auto chain: set POMHEALER_MCP_AUTO=1 in .env, then pytest tests/ -v

python -m pomhealer.review --list
python -m pomhealer.review --patch P-<id> --decision heal
python -m pomhealer.review --summary
```

## Slash skills (Cursor)

| Command | Purpose |
|---------|---------|
| `/architecture-discovery` | Refresh `pomhealer-artifacts/architecture/manifest.json` |
| `/pomhealer-init` | Bootstrap pomhealer in a consumer POM repo |
| `/pomhealer-propose` | Create patch proposals from failures |
| `/playwright-locator-repair` | MCP diagnosis + write `P-*.json` proposals |
| `/pomhealer-review` | Human approve / skip / apply via `pom_apply` |

## CI

GitHub Actions runs **test** → **propose-on-failure** (on failure) → **pomhealer-gates** (full queue checks after propose).

Local:

```bash
pytest tests/ -q
python -m pomhealer.architecture_scan
python -m pomhealer.ci_gates
# or
bash scripts/run_ci_gates.sh
```

## Branch policy

Repository: [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

- **`dev`** — integration and pomhealer work
- **`main`** — PR + green **Healing Framework CI** (`test` + `pomhealer-gates`)

See [AGENTS.md](AGENTS.md) and GitHub branch protection for `main`.

## Layout

```text
pages/              # locators + methods (single source of truth)
tests/              # tests use page-object fixtures
pomhealer/          # Python package: capture, queue, propose, review, apply
pomhealer-artifacts/  # runtime root (config + generated artifacts)
  pomhealer.toml      # layout config
  failures/ ...     # generated (gitignored)
.cursor/skills/     # slash-command skills (installed from package templates)
.cursor/mcp.json    # Playwright MCP stub
```

## Healing flow demos (opt-in)

Two intentional locator breaks to exercise the full pipeline. See [docs/POMHEALER_DEMO.md](docs/POMHEALER_DEMO.md).

```bash
pytest tests/test_orangehrm_pomhealer.py --run-pomhealer-demo -v
# opens a visible browser (slow-mo 400ms; set POMHEALER_DEMO_SLOW_MO to change)
```

## Demo session test (deprecated)

Use [docs/POMHEALER_DEMO.md](docs/POMHEALER_DEMO.md) instead:

```bash
pytest tests/test_orangehrm_pomhealer.py --run-pomhealer-demo -v
```
