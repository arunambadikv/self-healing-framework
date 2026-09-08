---
name: pomhealer-init
description: Bootstrap the Playwright pomhealer package in a consumer POM framework (pomhealer-artifacts/pomhealer.toml, artifacts, Cursor skills, MCP stub, .env.example). Use when the user runs /pomhealer-init or asks to set up pomhealer in their repo.
disable-model-invocation: true
---

# Healing Init

## Objective

Wire the installable `pomhealer` package into the current Playwright Python POM project.

## Prerequisites

```bash
pip install -e .
# or from another repo:
# pip install "pomhealer @ git+https://github.com/arunambadikv/self-healing-framework.git"
playwright install chromium
```

## Steps

1. Run from the consumer project root:

```bash
pomhealer-init
# or:
python -m pomhealer.init
# optional live MCP probe:
pomhealer-init --verify-mcp
```

2. Confirm outputs:
   - `pomhealer-artifacts/pomhealer.toml` (layout: pages/tests + pomhealer-artifacts)
   - `pomhealer-artifacts/{failures,pomhealer-queue,architecture,pomhealer-reports,auth}/`
   - `.cursor/skills/` operator skills (copied from package templates)
   - `.cursor/mcp.json` Playwright MCP stub (if missing)
   - `.env.example` (copy to `.env`; set `POMHEALER_LLM_PROVIDER` + matching API key for MCP propose)
   - Doctor report (use `--no-check` to skip)

3. Tell the user:
   - Full guide: `docs/CONSUMER_SETUP.md` in the pomhealer repo (or README link)
   - `cp .env.example .env` and set provider + key if they want automated propose
     (`cursor`/`openai`/`gemini`/`groq`/`litellm`; defaults `composer-2.5` / `gpt-4.1` /
     `gemini-3.6-flash` / `openai/gpt-oss-120b` / `gpt-4o-mini`)
   - `pomhealer-doctor` anytime to re-check
   - Capture/review/apply work without the API key
   - `pomhealer-init` refreshes bundled skills and `.env.example` from the package (even without `--force`)
   - After `pip install -U` from git, the next pytest / pomhealer-doctor does the same
   - `--force` overwrites `pomhealer-artifacts/pomhealer.toml` and `.cursor/mcp.json`

4. Ensure pytest loads the plugin (entry point via install, or):

```ini
[pytest]
addopts = -p pomhealer.pytest_plugin
```

## Rules

- Bundled Cursor skills and `.env.example` refresh from the package on init and after pip update (pytest / doctor). `--force` overwrites `pomhealer.toml` and `.cursor/mcp.json`.
- Do not edit consumer `pages/*.py` during init.
- Prefer `pomhealer-init` CLI over hand-copying files.
- Skills install to `.cursor/skills/` (Cursor default); runtime config/artifacts live under `pomhealer-artifacts/` so they do not collide with the Python package named `pomhealer`.
