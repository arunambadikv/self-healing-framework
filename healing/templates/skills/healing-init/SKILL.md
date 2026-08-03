---
name: healing-init
description: Bootstrap the Playwright healing package in a consumer POM framework (healer-artifacts/healing.toml, artifacts, Cursor skills, MCP stub). Use when the user runs /healing-init or asks to set up healing in their repo.
disable-model-invocation: true
---

# Healing Init

## Objective

Wire the installable `healing` package into the current Playwright Python POM project.

## Prerequisites

```bash
pip install -e ".[mcp]"
# or from another repo:
# pip install "healing @ git+https://github.com/arunambadikv/self-healing-framework.git"
# pip install "healing[mcp] @ git+https://github.com/arunambadikv/self-healing-framework.git"
```

## Steps

1. Run from the consumer project root:

```bash
healing-init
# or:
python -m healing.init
```

2. Confirm outputs:
   - `healer-artifacts/healing.toml` (layout: pages/tests + healer-artifacts)
   - `healer-artifacts/{failures,healing-queue,architecture,healing-reports,auth}/`
   - `.cursor/skills/` operator skills (copied from package templates)
   - `.cursor/mcp.json` Playwright MCP stub (if missing)
   - Optional first `architecture_scan` when `pages/` exists

3. Ensure pytest loads the plugin (entry point via install, or):

```ini
[pytest]
addopts = -p healing.pytest_plugin
```

4. Tell the user next steps: run a failing locator test → `/healing-propose` → `/healing-review`.

## Rules

- Do not overwrite existing skills/config unless the user asks for `--force`.
- Do not edit consumer `pages/*.py` during init.
- Prefer `healing-init` CLI over hand-copying files.
- Skills install to `.cursor/skills/` (Cursor default); runtime config/artifacts live under `healer-artifacts/` so they do not collide with the Python package named `healing`.
