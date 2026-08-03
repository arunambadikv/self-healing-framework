---
name: architecture-discovery
description: Scan the Playwright POM project and build or refresh healer-artifacts/architecture/manifest.json and manifest.md mapping pages, locators, tests, and data. Use when the user runs /architecture-discovery or asks where locators, page methods, and tests live. Also used by the daily architecture heartbeat.
disable-model-invocation: true
---

# Architecture Discovery

## Objective

Produce a one-time (refreshable) architecture manifest for the healing pipeline.

## Steps

1. Run: `python -m healing.architecture_scan` (from repo root).
2. Read outputs:
   - `healer-artifacts/architecture/manifest.json` (machine)
   - `healer-artifacts/architecture/manifest.md` (human)
3. If `content_hash` unchanged vs previous manifest, report **manifest up to date**.
4. Otherwise summarize: page classes, locator properties, test → page method usage.

## Heartbeat mode (daily)

Same scan command — no page/test edits. Report only:

- previous vs new `content_hash`
- whether anything under `pages/`, `tests/`, or `data/` changed

**Schedulers:**

- **Cursor Automation** — daily schedule; see [docs/ARCHITECTURE_HEARTBEAT.md](../../docs/ARCHITECTURE_HEARTBEAT.md)
- **GitHub Actions** — `.github/workflows/architecture-heartbeat.yml` (cron `0 6 * * *` UTC + `workflow_dispatch`)

## What the manifest contains

- `pages`: class → file, properties (locator id → line, expression summary), public methods
- `tests`: file → page classes used, method names referenced
- `data`: files under `data/` if present
- `generated_at`, `content_hash`

## Rules

- Do not edit tests or page files during discovery-only runs unless user asks to fix scan gaps.
- Prefer manifest paths when proposing patches (never guess file locations).
