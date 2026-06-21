# Project Status

> **Last updated:** 2026-06-09  
> **Branch:** `dev` (`cd38e51`) — 1 commit ahead of `main`  
> **Repo:** [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

## Summary

Playwright Python POM healing framework on the SeleniumBase demo page. Tests use a single page object (`DemoPage`); locator failures are captured automatically, classified, queued, and repaired through a propose → MCP verify → human review → apply pipeline. **Human review is required** before any change lands in `pages/*.py`.

**Current focus:** `dev` has the MCP propose runner and failure-gated `HEALING_MCP_AUTO` chain; merge to `main` via PR when CI is green.

---

## Phase checklist

| Phase | Status | Module / artifact |
|-------|--------|-------------------|
| POM tests + `demo` fixture | Done | `pages/`, `tests/conftest.py` |
| Step trace on page actions | Done | `healing/step_trace.py`, `pages/base_page.py` |
| Failure capture (F-*) | Done | `healing/failure_report.py`, `tests/conftest.py` |
| Failure classification | Done | `healing/failure_classifier.py` |
| Architecture scan + manifest | Done | `healing/architecture_scan.py` → `artifacts/architecture/` |
| Stub patch propose (P-*) | Done | `healing/pom_propose.py` |
| MCP propose (Cursor SDK) | Done | `healing/mcp_propose_runner.py` (needs `CURSOR_API_KEY`) |
| Post-test auto chain (opt-in) | Done | `healing/post_test.py`, `healing/session_state.py` |
| Human review + apply | Done | `healing/healing_review.py`, `healing/pom_apply.py` |
| CI: test → propose-on-failure → gates | Done | `.github/workflows/healing-ci.yml` |
| Healing flow demo tests | Done | `tests/test_healing_flow_demo.py`, `docs/HEALING_DEMO.md` |
| Auto-apply without review | Out of scope | By design |
| Legacy SmartPage / registry | Retired | `legacy/` (reference only) |

---

## Architecture

### Layout

```text
pages/                 # Locators (@property) + methods — single source of truth
tests/                 # Tests via `demo` fixture only (CI policy enforced)
healing/               # Capture, queue, propose, review, apply, CI gates
.cursor/skills/        # Slash-command operator skills
artifacts/             # Generated (gitignored): failures, queue, architecture, reports
docs/                  # Runbooks and this status file
```

### Page objects

| Class | File | Locator properties | Public methods | Notes |
|-------|------|-------------------:|---------------:|-------|
| `BasePage` | `pages/base_page.py` | — | `goto`, `_click_locator`, `_expect_visible`, … | Step tracing, shared actions |
| `DemoPage` | `pages/demo_page.py` | 30 | 57 | Demo app coverage + 2 intentional healing-demo locators |

**Machine-readable detail:** run `python -m healing.architecture_scan` → [`artifacts/architecture/manifest.json`](../artifacts/architecture/manifest.json) and [`manifest.md`](../artifacts/architecture/manifest.md) (generated; not in git).

### Test suite

| Group | Files | Tests (collected) | CI default |
|-------|-------|------------------:|------------|
| Demo coverage | `tests/test_demo_*.py` (8 files) | 10 | Runs |
| Raw Playwright policy test | `tests/test_demo_raw_playwright.py` | 1 | Runs (expect CI policy gate) |
| Healing pipeline demo | `tests/test_healing_flow_demo.py` | 2 | Skipped (`--run-healing-demo`) |
| Deprecated demo session | `tests/test_demo_total_failure.py` | 1 | Skipped (`--run-demo-session`) |
| Unit / integration | `tests/test_pom_healing_unit.py` | 9 | Runs |
| **Total** | 11 files | **21** | **18** in normal `pytest tests/` |

**Target app:** [SeleniumBase demo page](https://seleniumbase.io/demo_page) (`HEALING_BASE_URL` override supported).

### Healing pipeline modules

| Module | Role |
|--------|------|
| `failure_report.py` | Build and save `F-*.json` / `.md` on pytest failure |
| `failure_classifier.py` | `selector_break`, `network`, `app_regression`, … |
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
pending_proposal → awaiting_agent → patch_ready → applied | skipped | not_healable
```

### Cursor skills

| Skill | Purpose |
|-------|---------|
| `/architecture-discovery` | Refresh architecture manifest |
| `/healing-propose` | Turn failures into patch proposals |
| `/playwright-locator-repair` | MCP diagnosis + `P-*.json` shape |
| `/healing-review` | Human approve / skip / apply |

---

## Runtime artifacts (gitignored)

| Path | Contents |
|------|----------|
| `artifacts/failures/F-*.json` | Failure payload (`classification`, `healable`, steps) |
| `artifacts/failures/F-*.md` | Human-readable failure report |
| `artifacts/healing-queue/index.json` | **Canonical queue status** |
| `artifacts/healing-queue/patches/P-*.json` | Patch proposals |
| `artifacts/healing-queue/applied/` | Applied patches |
| `artifacts/healing-queue/skipped/` | Skipped + RCA |
| `artifacts/architecture/manifest.json` | Scanned pages, locators, tests |
| `artifacts/healing-reports/*.json` | Capture / propose / apply events |

**Inspect live queue:**

```bash
python -m healing.healing_review --list
python -m healing.pom_propose --list
python -m healing.mcp_propose_runner --list
cat artifacts/healing-queue/index.json
```

---

## Branch and CI

| Branch | Role | Notes |
|--------|------|-------|
| `dev` | Integration / healing work | Latest: MCP propose + failure-gated auto chain |
| `main` | Stable | Last merge: PR #1 from `dev` |

**GitHub Actions** (on push/PR to `main` / `master`):

1. **test** — `pytest`, architecture scan, upload artifacts  
2. **propose-on-failure** — stub + `mcp_propose_runner` (needs `CURSOR_API_KEY` secret)  
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

# Opt-in auto chain (healable failures in session only)
export HEALING_MCP_AUTO=1
export CURSOR_API_KEY=cursor_...
pytest tests/test_healing_flow_demo.py::test_healing_demo_github_link --run-healing-demo -v

# End-to-end demo runbook
# → docs/HEALING_DEMO.md
```

---

## Update log

| Date | Change |
|------|--------|
| 2026-06-09 | Added `docs/PROJECT_STATUS.md`; documented MCP propose pipeline and failure-gated `HEALING_MCP_AUTO` on `dev` |
| 2026-06-09 | Migrated to POM fail-fast healing pipeline on `dev` |
| Earlier | Initial self-healing framework; legacy SmartPage moved to `legacy/` |

---

## When to update this file

- Milestone or phase completed / scope changed  
- New page class, major test area, or healing module added  
- CI workflow or branch policy changed  
- `dev` merged to `main` (refresh branch table and “open items”)  
- Do **not** duplicate locator line numbers here — use `architecture_scan` manifest instead
