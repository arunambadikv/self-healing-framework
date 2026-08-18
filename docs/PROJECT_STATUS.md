# Project Status

> **Last updated:** 2026-08-18  
> **Branch:** `dev`  
> **Repo:** [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

## Summary

Playwright Python POM healing framework, now **installable** (`pip install -e ".[mcp]"` / git URL) with `/healing-init` for consumer frameworks. Tests use page-object fixtures; locator failures are captured automatically, classified, queued, and repaired through propose → MCP verify → human review → apply. **Human review is required** before any change lands in `pages/*.py` (decision once; agent executes with `--yes`).

**Hardening (2026-08):** apply validation allowlist + rollback; patch structure/`before` source checks; packaged `ci_gates_config.yaml` for pip consumers; pinned `@playwright/mcp@0.0.79`; queue `fcntl` lock + atomic index writes; `--json` / `--list-deferred` CLIs; doctor pages/.env checks.

**CI import (2026-08-18):** `healing-import` / auto-merge on `healing-review` copies `gh run download` dirs into `healer-artifacts/` and rewrites runner paths. Playwright browsers pin to `.playwright-browsers/` so Cursor sandbox caches are not used.
**Target app:** configurable via `HEALING_BASE_URL` (default: OrangeHRM demo login). Opt-in healing demos in `tests/test_orangehrm_healing.py` and `tests/test_saucedemo_healing.py`.

**Current focus:** `dev` has the MCP propose runner and failure-gated `HEALING_MCP_AUTO` chain; merge to `main` via PR when CI is green.

---

## Phase checklist

| Phase | Status | Module / artifact |
|-------|--------|-------------------|
| POM tests + page fixtures | Done | `pages/`, `tests/conftest.py` |
| Step trace on page actions | Done | `healing/step_trace.py`, `healing/playwright_trace.py` (auto Locator/Page patch), optional `healing/base_page.py` |
| Failure capture (F-*) | Done | `healing/failure_report.py`, `healing/pytest_plugin.py` |
| Failure classification | Done | `healing/failure_classifier.py` (incl. `auth_failure`) |
| Architecture scan + manifest | Done | `healing/architecture_scan.py` → `healer-artifacts/architecture/` |
| Architecture daily heartbeat | Done | GHA cron + Cursor Automation draft ([docs/ARCHITECTURE_HEARTBEAT.md](ARCHITECTURE_HEARTBEAT.md)) |
| Stub patch propose (P-*) | Done | `healing/pom_propose.py` |
| MCP propose (multi-LLM + Playwright MCP) | Done | `healing/mcp_propose_runner.py` (`HEALING_LLM_PROVIDER` + key) |
| Post-test auto chain (opt-in) | Done | `healing/post_test.py`, `healing/session_state.py` |
| Human review + apply | Done | `healing/healing_review.py` (`--yes`, screenshots, deferred) |
| CI artifact import | Done | `healing/artifact_import.py` (`healing-import`; auto on review) |
| Installable package + init | Done | `pyproject.toml`, `healing/init.py`, `/healing-init` |
| Consumer setup guide + doctor | Done | [docs/CONSUMER_SETUP.md](CONSUMER_SETUP.md), `healing-doctor` |
| QA Chapters Confluence pack | Done | [docs/CONFLUENCE_QA_CHAPTERS.md](CONFLUENCE_QA_CHAPTERS.md) + [docs/attachments/](attachments/) |
| CI: test → propose-on-failure → gates | Done | `.github/workflows/healing-ci.yml` (incl. `dev`) |
| Remote pipeline E2E | Done | `.github/workflows/healing-pipeline-e2e.yml` |
| Healing flow demo tests | Done | OrangeHRM + SauceDemo (+ inventory auth) |
| Apply allowlist + rollback | Done | `healing/pom_apply.py` (no `shell=True`) |
| Patch validators + source `before` check | Done | `healing/patch_validate.py` |
| Packaged gate/MCP config for consumers | Done | `healing/gates_config.py` + package data |
| Queue lock + deferred listing | Done | `healing_queue` flock; `--list-deferred` |
| Auto-apply without review | Out of scope | By design |
| Legacy SmartPage / registry | Retired | Removed; locators live on page objects only |
| PyPI publish | Later | Git/editable install first |

---

## Architecture

### Layout

```text
pages/                 # Locators (@property) + methods — single source of truth
tests/                 # Tests via page-object fixtures (CI policy enforced)
healing/               # Python package: capture, queue, propose, review, apply, CI gates
healer-artifacts/      # Runtime root (config + generated artifacts; not the import package)
  healing.toml         # Canonical layout config
  failures/ ...        # Generated (gitignored): queue, architecture, reports, auth
.cursor/skills/        # Slash-command operator skills (from package templates)
docs/                  # Runbooks and this status file
```

### Page objects

| Class | File | Notes |
|-------|------|-------|
| `BasePage` | `pages/base_page.py` (re-exports `healing.base_page`) | Optional helpers; auto-trace via `playwright_trace` |
| `OrangeHrmLoginPage` | `pages/orangehrm_login_page.py` | Login + healing demo locator |
| `OrangeHrmDashboardPage` | `pages/orangehrm_dashboard_page.py` | Post-login healing demo |
| `SauceDemoLoginPage` | `pages/saucedemo_login_page.py` | Sauce Demo login healing demo |
| `SauceDemoInventoryPage` | `pages/saucedemo_inventory_page.py` | Post-login inventory healing demo |
| `DemoPage` | `pages/demo_page.py` | Legacy reference / unit tests |

**Machine-readable detail:** run `python -m healing.architecture_scan` → [`healer-artifacts/architecture/manifest.json`](../healer-artifacts/architecture/manifest.json) and [`manifest.md`](../healer-artifacts/architecture/manifest.md) (generated; not in git).

### Test suite

| Group | Files | CI default |
|-------|-------|------------|
| Healing pipeline demo | `tests/test_orangehrm_healing.py`, `tests/test_saucedemo_healing.py` | Skipped (`--run-healing-demo`) |
| Unit / integration | `tests/test_pom_healing_unit.py`, `tests/test_healing_review_interactive.py` | Runs |

**Target app:** `HEALING_BASE_URL` (default OrangeHRM demo login).

### Healing pipeline modules

| Module | Role |
|--------|------|
| `artifact_naming.py` | Readable `F-`/`P-` ids from test name + UTC stamp |
| `failure_report.py` | Build and save `F-{test}-{stamp}.json` / `.md` on pytest failure |
| `failure_classifier.py` | `selector_break`, `auth_failure`, `network`, `app_regression`, … |
| `init.py` | `healing-init` bootstrap for consumer frameworks |
| `doctor.py` | `healing-doctor` consumer setup checks (+ optional `--verify-mcp`) |
| `config.py` / `paths.py` | Workspace-aware layout + `healer-artifacts/healing.toml` / `[tool.healing]` |
| `healing_queue.py` | Queue index, status machine, `index.json` |
| `architecture_scan.py` | AST scan of `pages/`, `tests/`, `data/` |
| `pom_propose.py` | Stub `P-*.json` + agent task from failures |
| `mcp_propose_runner.py` | Complete patches via Cursor SDK + Playwright MCP |
| `post_test.py` | Opt-in session-end chain (`HEALING_MCP_AUTO`) |
| `session_state.py` | In-session healable-failure counter (gates auto chain) |
| `healing_review.py` | Human heal / skip / defer |
| `pom_apply.py` | Apply `architecture_updates` to `pages/*.py` |
| `healing_reports.py` | Per-module event log for CI ratio monitoring |
| `ci_gates.py` | Policy + queue thresholds |
| `pytest_plugin.py` | `--healing-scan-architecture`, session finish hook |

### Queue status flow

```text
pending_proposal → awaiting_agent → patch_ready → applied | skipped | deferred | not_healable
```

### Cursor skills

| Skill | Purpose |
|-------|---------|
| `/architecture-discovery` | Refresh architecture manifest (also daily heartbeat) |
| `/healing-init` | Bootstrap healing in a consumer POM repo |
| `/healing-propose` | Turn failures into patch proposals |
| `/playwright-locator-repair` | MCP diagnosis + `P-*.json` shape |
| `/healing-review` | Human approve / skip / apply (one decision → CLI `--yes`) |

---

## Runtime artifacts (gitignored)

| Path | Contents |
|------|----------|
| `healer-artifacts/failures/F-{test}-{stamp}.json` | Failure payload (`classification`, `healable`, steps); stamp = `YYYYMMDD-HHMMSS` |
| `healer-artifacts/failures/F-{test}-{stamp}.md` | Human-readable failure report |
| `healer-artifacts/failures/screenshot-F-….png` | Failure screenshot (same id) |
| `healer-artifacts/healing-queue/index.json` | **Canonical queue status** |
| `healer-artifacts/healing-queue/patches/P-{test}-{stamp}.json` | Patch proposals |
| `healer-artifacts/healing-queue/applied/` | Applied patches |
| `healer-artifacts/healing-queue/skipped/` | Skipped + RCA |
| `healer-artifacts/architecture/manifest.json` | Scanned pages, locators, tests |
| `healer-artifacts/healing-reports/*.json` | Capture / propose / apply events |

**Inspect live queue:**

```bash
python -m healing.healing_review --list
python -m healing.pom_propose --list
python -m healing.mcp_propose_runner --list
cat healer-artifacts/healing-queue/index.json
```

---

## Branch and CI

| Branch | Role | Notes |
|--------|------|-------|
| `dev` | Integration / healing work | Latest: MCP propose + failure-gated auto chain |
| `main` | Stable | Last merge: PR #1 from `dev` |

**GitHub Actions** (on push/PR to `main` / `master`):

1. **test** — `pytest`, architecture scan, upload artifacts  
2. **propose-on-failure** — stub + `mcp_propose_runner` (needs provider secret: `CURSOR_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`)  
3. **healing-gates** — `python -m healing.ci_gates`

**Open item:** PR `dev` → `main` for commit `cd38e51`.

---

## Operator quick reference

```bash
# Normal test run
pytest tests/ -v

# After healable locator failure (manual)
python -m healing.architecture_scan
python -m healing.pom_propose --process-all
python -m healing.mcp_propose_runner --process-all
python -m healing.healing_review --patch P-<id> --decision heal

# Opt-in auto chain (new stub per session failure; MCP + review prefer latest patch)
export HEALING_MCP_AUTO=1
# set HEALING_LLM_PROVIDER + matching key in .env
pytest tests/test_orangehrm_healing.py::test_orangehrm_broken_login_button --run-healing-demo -v

# End-to-end demo runbook
# → docs/HEALING_DEMO.md
```

---

## Update log

| Date | Change |
|------|--------|
| 2026-08-12 | Multi-provider propose (`cursor`/`openai`/`anthropic`); CI + consumer git docs |
| 2026-08-06 | High/medium hardening: apply security, patch validate, MCP pin, package config, queue lock, DX CLIs |
| 2026-07-22 | Always create new stubs per failure; MCP/review prefer latest patch (newest-first; one MCP per architecture_ref) |
| 2026-07-22 | Auto chain scoped to this session's failures + newly created stubs; classifier treats chrome-error/goto as non-healable |
| 2026-06-09 | Added `docs/PROJECT_STATUS.md`; documented MCP propose pipeline and failure-gated `HEALING_MCP_AUTO` on `dev` |
| 2026-06-09 | Migrated to POM fail-fast healing pipeline on `dev` |
| Earlier | Initial self-healing framework; legacy SmartPage / registry retired |

---

## When to update this file

- Milestone or phase completed / scope changed  
- New page class, major test area, or healing module added  
- CI workflow or branch policy changed  
- `dev` merged to `main` (refresh branch table and “open items”)  
- Do **not** duplicate locator line numbers here — use `architecture_scan` manifest instead
