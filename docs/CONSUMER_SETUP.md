# Consumer setup — Pomhealer package

Guide for using the installable `pomhealer` package inside **your** Playwright Page Object Model project.

Operator details for this reference repo: [AGENTS.md](../AGENTS.md)  
Project status: [PROJECT_STATUS.md](PROJECT_STATUS.md)

---

## Requirements

| Requirement | When needed | Notes |
|-------------|-------------|--------|
| Python **3.10+** | Always | |
| pip + venv | Always | |
| `pomhealer` | Always | Core package includes Cursor / OpenAI / Gemini / Groq SDKs |
| Chromium via Playwright | Running real browser tests | `playwright install chromium` |
| Node.js 18+ / **`npx`** | Automated MCP propose | Playwright MCP runs via pinned `@playwright/mcp` |
| **`POMHEALER_LLM_PROVIDER` + matching key** | Automated MCP propose only | `cursor`→`CURSOR_API_KEY`, `openai`→`OPENAI_API_KEY`, `gemini`→`GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `groq`→`GROQ_API_KEY`, `litellm`→`LITE_LLM_KEY` (Keyvalue Lite LLM proxy). Defaults: `composer-2.5` / `gpt-4.1` / `gemini-3.6-flash` / `openai/gpt-oss-120b` / `gpt-4o-mini` (override with `POMHEALER_LLM_MODEL`) |
| Cursor IDE + MCP panel | Interactive slash-skill browser repair | **Not** required for CLI/`mcp_propose_runner` |

**Not required** for failure capture, architecture scan, stub propose, human review, or apply: API key, Node, or Cursor MCP settings.

Set `POMHEALER_LLM_PROVIDER` and the matching key in `.env`. You do **not** install extra pip extras for providers.

---

## Quick start (happy path)

```bash
# 1. In your POM project
python -m venv .venv && source .venv/bin/activate

# 2. Install the package
pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
# Same machine / local checkout:
# pip install -e "/path/to/self-healing-framework"

# 3. Browser binaries
playwright install chromium

# 4. Bootstrap layout + skills + doctor
pomhealer-init

# 5. Secret for automated propose (optional until you need MCP propose)
cp .env.example .env
# edit .env → POMHEALER_LLM_PROVIDER=cursor|openai|gemini|groq|litellm + matching API key

# 6. Re-check anytime
pomhealer-doctor
# optional live MCP probe (needs network):
# pomhealer-doctor --verify-mcp

# 7. Run your tests — failures are captured automatically
pytest tests/ -v
```

Optional auto chain after healable locator failures (`selector_break` only — network, auth, app regression, etc. are never auto-proposed):

```bash
# in .env (loaded automatically — no export needed):
# POMHEALER_MCP_AUTO=1
# POMHEALER_LLM_PROVIDER=cursor   # or openai | gemini | groq | litellm
# CURSOR_API_KEY=...            # or OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY / LITE_LLM_KEY
pytest tests/ -v
```

**CI from git install:** see [CONSUMER_CI.md](CONSUMER_CI.md) for a propose-on-failure workflow using the same secrets.

---

## Architecture discovery (automatic)

Architecture scan (`/architecture-discovery` / `pomhealer-scan`) runs automatically when:

1. You run **`pomhealer-init`** (first install / bootstrap), or
2. You **update** the `pomhealer` package and then run **`pytest`** (version stamp under `pomhealer-artifacts/architecture/`), or
3. The manifest is **stale** vs `pages/` / `tests/` / `data/`

After `pip install -U "pomhealer @ git+..."` the next **`pytest`**, **`pomhealer-doctor`**, **`pomhealer-review`**, or **`pomhealer-mcp-propose`** also refreshes packaged Cursor skills and `.env.example` (your `.env` is never overwritten). `pomhealer-init` refreshes those templates too; `--force` is only needed to replace `pomhealer.toml` / `.cursor/mcp.json`.

Manual: `pomhealer-scan` or `python -m pomhealer.architecture_scan`.

## What `pomhealer-init` creates

| Path | Purpose |
|------|---------|
| `pomhealer-artifacts/pomhealer.toml` | Layout config (`pages_dir`, `artifacts_dir`, …) |
| `pomhealer-artifacts/failures/` | Failure JSON/MD + screenshots |
| `pomhealer-artifacts/pomhealer-queue/` | Pending `patches/` plus `applied/` / `skipped/` after review |
| `pomhealer-artifacts/architecture/` | Manifest from scan |
| `pomhealer-artifacts/pomhealer-reports/` | Pipeline events |
| `pomhealer-artifacts/auth/` | Saved storage state (when used) |
| `.cursor/skills/` | Operator skills (also bundled in the package) |
| `.cursor/mcp.json` | Playwright MCP stub for Cursor / CLI |
| `.env.example` | Template for `POMHEALER_LLM_PROVIDER` / API keys / toggles |

Flags:

```bash
pomhealer-init                 # default: write files + run doctor
pomhealer-init --force         # also overwrite pomhealer.toml and .cursor/mcp.json
pomhealer-init --no-scan       # skip architecture scan
pomhealer-init --no-check      # skip doctor
pomhealer-init --verify-mcp    # doctor + npx Playwright MCP probe
```

Equivalent: `python -m pomhealer.init`

---

## What `pomhealer-doctor` checks

```bash
pomhealer-doctor
pomhealer-doctor --workspace /path/to/project
pomhealer-doctor --verify-mcp    # also runs: npx --yes @playwright/mcp@0.0.79 --help
pomhealer-doctor --strict        # exit 1 on warnings as well as errors
```

| Check | Typical meaning |
|-------|-----------------|
| pomhealer package | `import pomhealer` works |
| pytest plugin | `pytest11` entry `pomhealer` registered |
| LLM SDK | Cursor SDK + OpenAI-compatible client (Gemini/Groq use the same client) |
| chromium | Browser binary installed |
| npx (Node) | Available for Playwright MCP |
| mcp.json | `.cursor/mcp.json` present |
| LLM API key | Matching key for `POMHEALER_LLM_PROVIDER` |
| pomhealer.toml | Config under `pomhealer-artifacts/` (or `[tool.pomhealer]`) |
| pages dir | Page objects present |
| artifact dirs | Runtime folders exist |
| skills | Resolvable from workspace or package templates |

Warnings for API key / Node / MCP are OK if you only need capture → review → apply.

---

## CLI reference

Installed with the package (`pip install pomhealer`):

| Command | Module | Role |
|---------|--------|------|
| `pomhealer-init` | `pomhealer.init` | Bootstrap consumer project |
| `pomhealer-doctor` | `pomhealer.doctor` | Setup / dependency checks |
| `pomhealer-scan` | `pomhealer.architecture_scan` | Refresh architecture manifest |
| `pomhealer-propose` | `pomhealer.pom_propose` | Stub patches from failures |
| `pomhealer-mcp-propose` | `pomhealer.mcp_propose_runner` | Complete patches via LLM + Playwright MCP |
| `pomhealer-review` | `pomhealer.review` | List / heal / skip / defer (auto-imports CI downloads) |
| `pomhealer-import` | `pomhealer.artifact_import` | Merge `gh run download` dirs into `pomhealer-artifacts/` |
| `pomhealer-gates` | `pomhealer.ci_gates` | CI policy + queue gates |

---

## Capability matrix

| Capability | Command / trigger | Needs |
|------------|-------------------|--------|
| Auto-capture failures | `pytest` (plugin) | pip + chromium for browser tests |
| Architecture scan | `pomhealer-scan` | pip |
| Stub propose | `pomhealer-propose --process-all` | pip |
| MCP propose | `pomhealer-mcp-propose --process-all` | provider key, Node/`npx` |
| Auto chain | `POMHEALER_MCP_AUTO=1` in `.env`, then `pytest` | same as MCP propose |
| CI propose-on-failure | see [CONSUMER_CI.md](CONSUMER_CI.md) | repo secrets + git install |
| Human review / apply | `pomhealer-review --interactive` | pip |
| Import CI artifacts | `pomhealer-import` (also auto on `pomhealer-review`) | pip |
| Interactive slash skills | Cursor `/pomhealer-*` | skills + optional IDE MCP |

---

## Playwright MCP: CLI vs Cursor IDE

- **CLI / CI (`pomhealer-mcp-propose`):** starts Playwright MCP over **stdio** using `.cursor/mcp.json` (or built-in defaults). You do **not** need to enable MCP in Cursor Settings for this path.
- **Cursor IDE slash skills with live browser tools:** enable the Playwright server from `.cursor/mcp.json` in **Cursor → Settings → MCP**.

`.env` is loaded automatically for propose (via `python-dotenv`). Prefer `.env` over exporting the key every session.

---

## Expected project layout (after init)

```text
your-pom-project/
  pages/                 # your page objects (you own these)
  tests/                 # your tests
  pomhealer-artifacts/
    pomhealer.toml
    failures/
    pomhealer-queue/
    architecture/
    pomhealer-reports/
    auth/
  .cursor/
    skills/              # pomhealer-* skills from the package
    mcp.json
  .env.example
  .env                   # local only — gitignore this
```

Do **not** create a top-level folder named `pomhealer/` for reports — that can shadow the installed Python package. Use `pomhealer-artifacts/`.

Page objects may call `page.locator(...).click()` directly. The installed pytest plugin auto-instruments Playwright `Locator`/`Page` actions and records `test_steps` from `pages/*.py` stack frames — no consumer helpers required. `pomhealer.base_page.BasePage` is optional (timeouts, retries, explicit `locator_id` names). Traceback inference remains a fallback if instrumentation misses.

---

## Manual pomhealer workflow

```bash
pytest tests/ -v
pomhealer-scan
pomhealer-propose --process-all
pomhealer-mcp-propose --process-all    # needs POMHEALER_LLM_PROVIDER + matching API key
pomhealer-review --list
pomhealer-review --interactive         # or --patch P-<id> --decision heal
```

Artifacts:

- Failures: `pomhealer-artifacts/failures/F-{test-name}-{YYYYMMDD-HHMMSS}.json`
- Pending patches: `pomhealer-artifacts/pomhealer-queue/patches/P-{test-name}-{YYYYMMDD-HHMMSS}.json`
- After heal/skip: those files (json, md, agent-task) move to `pomhealer-queue/applied/` or `skipped/`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No failure files after pytest | Confirm `import pomhealer` and `pomhealer-doctor` shows pytest plugin OK; reinstall package |
| LLM API key required / propose failed | Set `POMHEALER_LLM_PROVIDER` and matching `CURSOR_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` / `LITE_LLM_KEY` in `.env`. Use current defaults (`gemini-3.6-flash`, `openai/gpt-oss-120b`, `gpt-4o-mini`) — older Groq/Gemini IDs were retired. For `litellm`, VPN may be required outside office (Keyvalue IP whitelist). |
| Groq 413 / TPM / request too large | Free-tier Groq is ~8k tokens/minute; wait a minute and retry `mcp_propose_runner --patch-id P-<id>`. |
| Applied patch still in `patches/` | Heal/skip archives json/md/agent-task into `applied/` or `skipped/`. Re-run `pomhealer-review --list` to sweep CI re-imports. |
| MCP / npx errors | Install Node 18+; run `pomhealer-doctor --verify-mcp` |
| Chromium missing | Set `PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers` in `.env`, then `playwright install chromium`. Cursor sandbox `/tmp/cursor-sandbox-cache` is ephemeral. |
| CI download not in pomhealer-artifacts | `gh run download` unpacks under the artifact name; run `pomhealer-review` or `pomhealer-import` to merge |
| Skills missing / outdated after git install | Run `pytest` or `pomhealer-doctor` (auto-refresh) or `pomhealer-init` |
| Import errors / wrong package | Ensure project root is not a local empty `pomhealer/` reports directory |

---

## Install variants

```bash
# From GitHub (default branch)
pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"

# Specific branch
pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git@dev"

# Editable local checkout (same machine as this repo)
pip install -e "/home/arun/playwright-healing-framework"
```
