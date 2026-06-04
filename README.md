# Playwright Python POM Healing Framework

Page Object Model tests (`pages/*.py`) with **fail-fast** execution and a **post-failure healing pipeline**: capture failures → MCP/agent patch proposals → human review → apply locator fixes in page objects only.

**Demo app:** [SeleniumBase demo page](https://seleniumbase.io/demo_page)

**Operator guide:** [AGENTS.md](AGENTS.md)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python -m healing.architecture_scan
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
# on failure → artifacts/failures/F-*.json + .md

python -m healing.architecture_scan
python -m healing.pom_propose --process-all
# Cursor Agent + Playwright MCP completes P-*.json in artifacts/healing-queue/patches/

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
- **`main`** — PR + green **Healing Framework CI** (`test-and-gates`)

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

## Demo session test (intentional failure)

```bash
pytest tests/test_demo_total_failure.py --run-demo-session -v
```
