# Agent Instructions — Playwright POM Healing Framework

## Architecture

- **Tests:** raw Playwright via `demo` fixture (`DemoPage` in [`pages/demo_page.py`](pages/demo_page.py))
- **Locators:** Python properties on page classes only (no `locator_registry.yaml` in runtime path)
- **Failures:** `artifacts/failures/F-*.json` + `.md` (auto on pytest failure)
- **Patches:** `artifacts/healing-queue/patches/P-*.json` (after MCP + agent)
- **Manifest:** `artifacts/architecture/manifest.json` (run scan before propose/review)

## Slash skills

| Skill | Command |
|-------|---------|
| Architecture scan | `/architecture-discovery` → `python -m healing.architecture_scan` |
| Propose patches | `/healing-propose` → `python -m healing.pom_propose --process-all` |
| Human review | `/healing-review` → `python -m healing.healing_review --list` |
| Locator repair (MCP + proposals) | `/playwright-locator-repair` |
| Human review + apply | `/healing-review` |

## Playwright MCP setup

```bash
bash scripts/setup_mcp_agent.sh
```

Connect Playwright MCP in Cursor (`.cursor/mcp.json`). Skills live in `.cursor/skills/`.

## Failure → patch → apply workflow

### 1. Test fails (automatic)

```bash
pytest tests/test_demo_buttons_links.py -v
# → artifacts/failures/F-<id>.json + .md
```

### 2. Refresh architecture context

```bash
python -m healing.architecture_scan
```

### 3. Propose patches (stub + agent task files)

```bash
python -m healing.pom_propose --list
python -m healing.pom_propose --process-all
# Cursor Agent: complete patches in artifacts/healing-queue/patches/ using MCP
```

Agent prompt per failure: `artifacts/healing-queue/patches/F-*-agent-task.md`

Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to fill real `architecture_updates` in `P-*.json`.

### 4. Human review

```bash
python -m healing.healing_review --list
python -m healing.healing_review --show P-<id>
python -m healing.healing_review --patch P-<id> --decision heal
python -m healing.healing_review --patch P-<id> --decision skip --reason "app regression"
python -m healing.healing_review --summary
```

### 5. CI

```bash
pytest tests/ -q
python -m healing.architecture_scan
python -m healing.ci_gates
```

## Demo session test (intentional failure)

```bash
pytest tests/test_demo_total_failure.py --run-demo-session -v
```

## Legacy

SmartPage + `locator_registry.yaml` moved to [`legacy/`](legacy/) for reference only.
