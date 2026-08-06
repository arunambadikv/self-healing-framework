# Consumer setup — Healing package

Guide for using the installable `healing` package inside **your** Playwright Page Object Model project.

Operator details for this reference repo: [AGENTS.md](../AGENTS.md)  
Project status: [PROJECT_STATUS.md](PROJECT_STATUS.md)

---

## Requirements

| Requirement | When needed | Notes |
|-------------|-------------|--------|
| Python **3.10+** | Always | |
| pip + venv | Always | |
| `healing` or `healing[mcp]` | Always | Core package |
| Chromium via Playwright | Running real browser tests | `playwright install chromium` |
| Node.js 18+ / **`npx`** | Automated MCP propose | Playwright MCP runs via `npx @playwright/mcp` |
| **`CURSOR_API_KEY`** | Automated MCP propose only | Put in `.env` (never commit `.env`) |
| Cursor IDE + MCP panel | Interactive slash-skill browser repair | **Not** required for CLI/`mcp_propose_runner` |

**Not required** for failure capture, architecture scan, stub propose, human review, or apply: API key, Node, or Cursor MCP settings.

---

## Quick start (happy path)

```bash
# 1. In your POM project
python -m venv .venv && source .venv/bin/activate

# 2. Install the package
pip install "healing[mcp] @ git+https://github.com/arunambadikv/self-healing-framework.git"
# Same machine / local checkout:
# pip install -e "/path/to/self-healing-framework[mcp]"

# 3. Browser binaries
playwright install chromium

# 4. Bootstrap layout + skills + doctor
healing-init

# 5. Secret for automated propose (optional until you need MCP propose)
cp .env.example .env
# edit .env → CURSOR_API_KEY=cursor_...

# 6. Re-check anytime
healing-doctor
# optional live MCP probe (needs network):
# healing-doctor --verify-mcp

# 7. Run your tests — failures are captured automatically
pytest tests/ -v
```

Optional auto chain after healable locator failures (`selector_break` only — network, auth, app regression, etc. are never auto-proposed):

```bash
# in .env (loaded automatically — no export needed):
# HEALING_MCP_AUTO=1
# CURSOR_API_KEY=cursor_...
pytest tests/ -v
```

---

## Architecture discovery (automatic)

Architecture scan (`/architecture-discovery` / `healing-scan`) runs automatically when:

1. You run **`healing-init`** (first install / bootstrap), or
2. You **update** the `healing` package and then run **`pytest`** (version stamp under `healer-artifacts/architecture/`), or
3. The manifest is **stale** vs `pages/` / `tests/` / `data/`

Manual: `healing-scan` or `python -m healing.architecture_scan`.

## What `healing-init` creates

| Path | Purpose |
|------|---------|
| `healer-artifacts/healing.toml` | Layout config (`pages_dir`, `artifacts_dir`, …) |
| `healer-artifacts/failures/` | Failure JSON/MD + screenshots |
| `healer-artifacts/healing-queue/` | Patch queue + patches |
| `healer-artifacts/architecture/` | Manifest from scan |
| `healer-artifacts/healing-reports/` | Pipeline events |
| `healer-artifacts/auth/` | Saved storage state (when used) |
| `.cursor/skills/` | Operator skills (also bundled in the package) |
| `.cursor/mcp.json` | Playwright MCP stub for Cursor / CLI |
| `.env.example` | Template for `CURSOR_API_KEY` / toggles |

Flags:

```bash
healing-init                 # default: write files + run doctor
healing-init --force         # overwrite existing skills/config
healing-init --no-scan       # skip architecture scan
healing-init --no-check      # skip doctor
healing-init --verify-mcp    # doctor + npx Playwright MCP probe
```

Equivalent: `python -m healing.init`

---

## What `healing-doctor` checks

```bash
healing-doctor
healing-doctor --workspace /path/to/project
healing-doctor --verify-mcp    # also runs: npx --yes @playwright/mcp@latest --help
healing-doctor --strict        # exit 1 on warnings as well as errors
```

| Check | Typical meaning |
|-------|-----------------|
| healing package | `import healing` works |
| pytest plugin | `pytest11` entry `healing` registered |
| cursor-sdk | Present when you installed `healing[mcp]` |
| chromium | Browser binary installed |
| npx (Node) | Available for Playwright MCP |
| mcp.json | `.cursor/mcp.json` present |
| CURSOR_API_KEY | Set in env or `.env` |
| healing.toml | Config under `healer-artifacts/` (or `[tool.healing]`) |
| artifact dirs | Runtime folders exist |
| skills | Resolvable from workspace or package templates |

Warnings for API key / Node / MCP are OK if you only need capture → review → apply.

---

## CLI reference

Installed with the package (`pip install healing` / `healing[mcp]`):

| Command | Module | Role |
|---------|--------|------|
| `healing-init` | `healing.init` | Bootstrap consumer project |
| `healing-doctor` | `healing.doctor` | Setup / dependency checks |
| `healing-scan` | `healing.architecture_scan` | Refresh architecture manifest |
| `healing-propose` | `healing.pom_propose` | Stub patches from failures |
| `healing-mcp-propose` | `healing.mcp_propose_runner` | Complete patches via Cursor SDK + Playwright MCP |
| `healing-review` | `healing.healing_review` | List / heal / skip / defer |
| `healing-gates` | `healing.ci_gates` | CI policy + queue gates |

---

## Capability matrix

| Capability | Command / trigger | Needs |
|------------|-------------------|--------|
| Auto-capture failures | `pytest` (plugin) | pip + chromium for browser tests |
| Architecture scan | `healing-scan` | pip |
| Stub propose | `healing-propose --process-all` | pip |
| MCP propose | `healing-mcp-propose --process-all` | `CURSOR_API_KEY`, Node/`npx`, `healing[mcp]` |
| Auto chain | `HEALING_MCP_AUTO=1` in `.env`, then `pytest` | same as MCP propose |
| Human review / apply | `healing-review --interactive` | pip |
| Interactive slash skills | Cursor `/healing-*` | skills + optional IDE MCP |

---

## Playwright MCP: CLI vs Cursor IDE

- **CLI / CI (`healing-mcp-propose`):** starts Playwright MCP over **stdio** using `.cursor/mcp.json` (or built-in defaults). You do **not** need to enable MCP in Cursor Settings for this path.
- **Cursor IDE slash skills with live browser tools:** enable the Playwright server from `.cursor/mcp.json` in **Cursor → Settings → MCP**.

`.env` is loaded automatically for propose (via `python-dotenv`). Prefer `.env` over exporting the key every session.

---

## Expected project layout (after init)

```text
your-pom-project/
  pages/                 # your page objects (you own these)
  tests/                 # your tests
  healer-artifacts/
    healing.toml
    failures/
    healing-queue/
    architecture/
    healing-reports/
    auth/
  .cursor/
    skills/              # healing-* skills from the package
    mcp.json
  .env.example
  .env                   # local only — gitignore this
```

Do **not** create a top-level folder named `healing/` for runtime files — that can shadow the installed Python package. Use `healer-artifacts/`.

Page objects may call `page.locator(...).click()` directly. The installed pytest plugin auto-instruments Playwright `Locator`/`Page` actions and records `test_steps` from `pages/*.py` stack frames — no consumer helpers required. `healing.base_page.BasePage` is optional (timeouts, retries, explicit `locator_id` names). Traceback inference remains a fallback if instrumentation misses.

---

## Manual healing workflow

```bash
pytest tests/ -v
healing-scan
healing-propose --process-all
healing-mcp-propose --process-all    # needs CURSOR_API_KEY
healing-review --list
healing-review --interactive         # or --patch P-<id> --decision heal
```

Artifacts:

- Failures: `healer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json`
- Patches: `healer-artifacts/healing-queue/patches/P-{test-name}-{YYYYMMDD-HHMMSS}.json`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No failure files after pytest | Confirm `import healing` and `healing-doctor` shows pytest plugin OK; reinstall package |
| `CURSOR_API_KEY required` | Copy `.env.example` → `.env`, set key, re-run propose |
| MCP / npx errors | Install Node 18+; run `healing-doctor --verify-mcp` |
| Chromium missing | `playwright install chromium` |
| Skills missing in Cursor | Re-run `healing-init` (or rely on package templates) |
| Import errors / wrong package | Ensure project root is not a local empty `healing/` directory |

---

## Install variants

```bash
# From GitHub (default branch)
pip install "healing[mcp] @ git+https://github.com/arunambadikv/self-healing-framework.git"

# Specific branch
pip install "healing[mcp] @ git+https://github.com/arunambadikv/self-healing-framework.git@dev"

# Editable local checkout (same machine as this repo)
pip install -e "/home/arun/playwright-healing-framework[mcp]"

# Without MCP propose SDK (capture/review only)
pip install "healing @ git+https://github.com/arunambadikv/self-healing-framework.git"
```
