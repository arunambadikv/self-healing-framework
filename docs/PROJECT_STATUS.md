# Project Status

> **Last updated:** 2026-09-08  
> **Branch:** `dev`  
> **Repo:** [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

## Summary

Playwright Python POM **pomhealer** framework (package rename from `healing` in v0.2.0), installable (`pip install -e .` / git URL) with `/pomhealer-init` for consumer frameworks. Tests use page-object fixtures; locator failures are captured automatically, classified, queued, and repaired through propose → MCP verify → human review → apply. **Human review is required** before any change lands in `pages/*.py` (decision once; agent executes with `--yes`).

**Rebrand (2026-09-08):** Python package / CLIs / env / artifacts are now `pomhealer` / `pomhealer-*` / `POMHEALER_*` / `pomhealer-artifacts/` so a reports folder cannot shadow the import package.

**Hardening (2026-08):** apply validation allowlist + rollback; patch structure/`before` source checks; packaged `ci_gates_config.yaml` for pip consumers; pinned `@playwright/mcp@0.0.79`; queue `fcntl` lock + atomic index writes; `--json` / `--list-deferred` CLIs; doctor pages/.env checks.

**CI import (2026-08-18):** `pomhealer-import` / auto-merge on `pomhealer-review` copies `gh run download` dirs into `pomhealer-artifacts/` and rewrites runner paths. Playwright browsers pin to `.playwright-browsers/` so Cursor sandbox caches are not used.

**Providers (2026-08-20):** `POMHEALER_LLM_PROVIDER=cursor|openai|gemini|groq|litellm`. Defaults: `composer-2.5`, `gpt-4.1`, `gemini-3.6-flash`, `openai/gpt-oss-120b`, `gpt-4o-mini`. Cursor SDK, OpenAI, and MCP ship in the core package — consumers only set provider + key in `.env`. `litellm` uses Keyvalue proxy (`https://llm.keyvalue.systems` + `LITE_LLM_KEY`).

**Queue archive (2026-08-19):** heal/skip moves `P-*.json`, `.md`, and `-agent-task.md` out of pending `pomhealer-queue/patches/` into `applied/` or `skipped/`. Review/import sweeps leftovers (including CI re-imports).
**Target app:** configurable via `POMHEALER_BASE_URL` (default: OrangeHRM demo login). Opt-in pomhealer demos in `tests/test_orangehrm_pomhealer.py` and `tests/test_saucedemo_pomhealer.py`.

**Current focus:** `dev` has MCP propose, git-install template refresh (v0.1.2), and failure-gated `POMHEALER_MCP_AUTO`; merge to `main` via PR when CI is green.

---

## Phase checklist

| Phase | Status | Module / artifact |
|-------|--------|-------------------|
| POM tests + page fixtures | Done | `pages/`, `tests/conftest.py` |
| Step trace on page actions | Done | `pomhealer/step_trace.py`, `pomhealer/playwright_trace.py` (auto Locator/Page patch), optional `pomhealer/base_page.py` |
| Failure capture (F-*) | Done | `pomhealer/failure_report.py`, `pomhealer/pytest_plugin.py` |
| Failure classification | Done | `pomhealer/failure_classifier.py` (incl. `auth_failure`) |
| Architecture scan + manifest | Done | `pomhealer/architecture_scan.py` → `pomhealer-artifacts/architecture/` |
| Architecture daily heartbeat | Done | GHA cron + Cursor Automation draft ([docs/ARCHITECTURE_HEARTBEAT.md](ARCHITECTURE_HEARTBEAT.md)) |
| Stub patch propose (P-*) | Done | `pomhealer/pom_propose.py` |
| MCP propose (multi-LLM + Playwright MCP) | Done | `pomhealer/mcp_propose_runner.py` (`POMHEALER_LLM_PROVIDER` + key) |
| Post-test auto chain (opt-in) | Done | `pomhealer/post_test.py`, `pomhealer/session_state.py` |
| Human review + apply | Done | `pomhealer/review.py` (`--yes`, screenshots, deferred) |
| CI artifact import | Done | `pomhealer/artifact_import.py` (`pomhealer-import`; auto on review) |
| Installable package + init | Done | `pyproject.toml`, `pomhealer/init.py`, `/pomhealer-init` |
| Consumer setup guide + doctor | Done | [docs/CONSUMER_SETUP.md](CONSUMER_SETUP.md), `pomhealer-doctor` |
| QA Chapters Confluence pack | Done | [docs/CONFLUENCE_QA_CHAPTERS.md](CONFLUENCE_QA_CHAPTERS.md) + [docs/attachments/](attachments/) |
| CI: test → propose-on-failure → gates | Done | `.github/workflows/pomhealer-ci.yml` (incl. `dev`) |
| Remote pipeline E2E | Done | `.github/workflows/pomhealer-pipeline-e2e.yml` |
| Healing flow demo tests | Done | OrangeHRM + SauceDemo (+ inventory auth) |
| Apply allowlist + rollback | Done | `pomhealer/pom_apply.py` (no `shell=True`) |
| Patch validators + source `before` check | Done | `pomhealer/patch_validate.py` |
| Packaged gate/MCP config for consumers | Done | `pomhealer/gates_config.py` + package data |
| Queue lock + deferred listing | Done | `queue` flock; `--list-deferred` |
| Auto-apply without review | Out of scope | By design |
| Legacy SmartPage / registry | Retired | Removed; locators live on page objects only |
| PyPI publish | Later | Git/editable install first |

---

## Architecture

### Layout

```text
pages/                 # Locators (@property) + methods — single source of truth
tests/                 # Tests via page-object fixtures (CI policy enforced)
pomhealer/             # Python package: capture, queue, propose, review, apply, CI gates
pomhealer-artifacts/      # Runtime root (config + generated artifacts; not the import package)
  pomhealer.toml         # Canonical layout config
  failures/ ...        # Generated (gitignored): queue, architecture, reports, auth
.cursor/skills/        # Slash-command operator skills (from package templates)
docs/                  # Runbooks and this status file
```

### Page objects

| Class | File | Notes |
|-------|------|-------|
| `BasePage` | `pages/base_page.py` (re-exports `pomhealer.base_page`) | Optional helpers; auto-trace via `playwright_trace` |
| `OrangeHrmLoginPage` | `pages/orangehrm_login_page.py` | Login + pomhealer demo locator |
| `OrangeHrmDashboardPage` | `pages/orangehrm_dashboard_page.py` | Post-login pomhealer demo |
| `SauceDemoLoginPage` | `pages/saucedemo_login_page.py` | Sauce Demo login pomhealer demo |
| `SauceDemoInventoryPage` | `pages/saucedemo_inventory_page.py` | Post-login inventory pomhealer demo |
| `DemoPage` | `pages/demo_page.py` | Legacy reference / unit tests |

**Machine-readable detail:** run `python -m pomhealer.architecture_scan` → [`pomhealer-artifacts/architecture/manifest.json`](../pomhealer-artifacts/architecture/manifest.json) and [`manifest.md`](../pomhealer-artifacts/architecture/manifest.md) (generated; not in git).

### Test suite

| Group | Files | CI default |
|-------|-------|------------|
| Healing pipeline demo | `tests/test_orangehrm_pomhealer.py`, `tests/test_saucedemo_pomhealer.py` | Skipped (`--run-pomhealer-demo`) |
| Unit / integration | `tests/test_pomhealer_unit.py`, `tests/test_pomhealer_review_interactive.py` | Runs |

**Target app:** `POMHEALER_BASE_URL` (default OrangeHRM demo login).

### Healing pipeline modules

| Module | Role |
|--------|------|
| `artifact_naming.py` | Readable `F-`/`P-` ids from test name + UTC stamp |
| `failure_report.py` | Build and save `F-{test}-{stamp}.json` / `.md` on pytest failure |
| `failure_classifier.py` | `selector_break`, `auth_failure`, `network`, `app_regression`, … |
| `init.py` | `pomhealer-init` bootstrap for consumer frameworks |
| `doctor.py` | `pomhealer-doctor` consumer setup checks (+ optional `--verify-mcp`) |
| `config.py` / `paths.py` | Workspace-aware layout + `pomhealer-artifacts/pomhealer.toml` / `[tool.pomhealer]` |
| `queue.py` | Queue index, status machine, `index.json` |
| `architecture_scan.py` | AST scan of `pages/`, `tests/`, `data/` |
| `pom_propose.py` | Stub `P-*.json` + agent task from failures |
| `mcp_propose_runner.py` | Complete patches via Cursor SDK + Playwright MCP |
| `post_test.py` | Opt-in session-end chain (`POMHEALER_MCP_AUTO`) |
| `session_state.py` | In-session healable-failure counter (gates auto chain) |
| `review.py` | Human heal / skip / defer |
| `pom_apply.py` | Apply `architecture_updates` to `pages/*.py` |
| `reports.py` | Per-module event log for CI ratio monitoring |
| `ci_gates.py` | Policy + queue thresholds |
| `pytest_plugin.py` | `--pomhealer-scan-architecture`, session finish hook |

### Queue status flow

```text
pending_proposal → awaiting_agent → patch_ready → applied | skipped | deferred | not_healable
```

### Cursor skills

| Skill | Purpose |
|-------|---------|
| `/architecture-discovery` | Refresh architecture manifest (also daily heartbeat) |
| `/pomhealer-init` | Bootstrap pomhealer in a consumer POM repo |
| `/pomhealer-propose` | Turn failures into patch proposals |
| `/playwright-locator-repair` | MCP diagnosis + `P-*.json` shape |
| `/pomhealer-review` | Human approve / skip / apply (one decision → CLI `--yes`) |

---

## Runtime artifacts (gitignored)

| Path | Contents |
|------|----------|
| `pomhealer-artifacts/failures/F-{test}-{stamp}.json` | Failure payload (`classification`, `healable`, steps); stamp = `YYYYMMDD-HHMMSS` |
| `pomhealer-artifacts/failures/F-{test}-{stamp}.md` | Human-readable failure report |
| `pomhealer-artifacts/failures/screenshot-F-….png` | Failure screenshot (same id) |
| `pomhealer-artifacts/pomhealer-queue/index.json` | **Canonical queue status** |
| `pomhealer-artifacts/pomhealer-queue/patches/P-{test}-{stamp}.json` | **Pending** proposals (+ `.md`, `-agent-task.md`) |
| `pomhealer-artifacts/pomhealer-queue/applied/` | Applied patches (json/md/agent-task moved out of pending) |
| `pomhealer-artifacts/pomhealer-queue/skipped/` | Skipped patches + RCA |
| `pomhealer-artifacts/architecture/manifest.json` | Scanned pages, locators, tests |
| `pomhealer-artifacts/pomhealer-reports/*.json` | Capture / propose / apply events |

**Inspect live queue:**

```bash
python -m pomhealer.review --list
python -m pomhealer.pom_propose --list
python -m pomhealer.mcp_propose_runner --list
cat pomhealer-artifacts/pomhealer-queue/index.json
```

---

## Branch and CI

| Branch | Role | Notes |
|--------|------|-------|
| `dev` | Integration / pomhealer work | Latest: MCP propose + failure-gated auto chain |
| `main` | Stable | Last merge: PR #1 from `dev` |

**GitHub Actions** (on push/PR to `main` / `master`):

1. **test** — `pytest`, architecture scan, upload artifacts  
2. **propose-on-failure** — stub + `mcp_propose_runner` (needs provider secret: `CURSOR_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY`)  
3. **pomhealer-gates** — `python -m pomhealer.ci_gates`

**Open item:** PR `dev` → `main` for commit `cd38e51`.

---

## Operator quick reference

```bash
# Normal test run
pytest tests/ -v

# After healable locator failure (manual)
python -m pomhealer.architecture_scan
python -m pomhealer.pom_propose --process-all
python -m pomhealer.mcp_propose_runner --process-all
python -m pomhealer.review --patch P-<id> --decision heal

# Opt-in auto chain (new stub per session failure; MCP + review prefer latest patch)
export POMHEALER_MCP_AUTO=1
# set POMHEALER_LLM_PROVIDER + matching key in .env
pytest tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button --run-pomhealer-demo -v

# End-to-end demo runbook
# → docs/POMHEALER_DEMO.md
```

---

## Update log

| Date | Change |
|------|--------|
| 2026-08-20 | Added `litellm` provider (`LITE_LLM_KEY` → `https://llm.keyvalue.systems`, default `gpt-4o-mini`); OpenAI provider unchanged |
| 2026-08-19 | v0.1.2: Gemini/Groq defaults, OpenAI-compat propose, archive applied/skipped out of pending `patches/`; pip git updates refresh bundled skills + `.env.example` on next pytest/doctor |
| 2026-08-18 | Propose providers: `cursor`/`openai`/`gemini`/`groq` (Anthropic removed); SDKs bundled in core package |
| 2026-08-06 | High/medium hardening: apply security, patch validate, MCP pin, package config, queue lock, DX CLIs |
| 2026-07-22 | Always create new stubs per failure; MCP/review prefer latest patch (newest-first; one MCP per architecture_ref) |
| 2026-07-22 | Auto chain scoped to this session's failures + newly created stubs; classifier treats chrome-error/goto as non-healable |
| 2026-06-09 | Added `docs/PROJECT_STATUS.md`; documented MCP propose pipeline and failure-gated `POMHEALER_MCP_AUTO` on `dev` |
| 2026-06-09 | Migrated to POM fail-fast pomhealer pipeline on `dev` |
| Earlier | Initial self-healing framework; legacy SmartPage / registry retired |

---

## When to update this file

- Milestone or phase completed / scope changed  
- New page class, major test area, or pomhealer module added  
- CI workflow or branch policy changed  
- `dev` merged to `main` (refresh branch table and “open items”)  
- Do **not** duplicate locator line numbers here — use `architecture_scan` manifest instead
