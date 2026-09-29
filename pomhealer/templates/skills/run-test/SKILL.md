---
name: run-test
description: >-
  Run a named pytest case with project env and Playwright browser bootstrap
  (venv, .env, PLAYWRIGHT_BROWSERS_PATH, Chromium install, --run-pomhealer-demo).
  Use when the user runs /run-test or asks to run a specific test by name.
disable-model-invocation: true
---

# Run Named Test (env + browsers)

## Objective

Run one pytest node the user names, with the same env/browser setup this framework needs. Do not heal or edit page objects.

## Input

User shares a test name: function (`test_saucedemo_broken_login_button`), `file::test`, or full node id.

## Steps

1. **Python runner** — prefer `.venv/bin/python -m pytest`. Never bare `pytest` (venv shebang may be stale). Fallback: `python3 -m pytest` only if `.venv` is missing.

2. **Load `.env`** before pytest:
   ```bash
   set -a && [ -f .env ] && . ./.env; set +a
   ```

3. **Browsers path** — honor `PLAYWRIGHT_BROWSERS_PATH` from `.env` (default `.playwright-browsers`). If unset but `.playwright-browsers/` exists, export `PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers` for the run. If Chromium is missing under that root:
   ```bash
   .venv/bin/python -m playwright install chromium
   ```

4. **Resolve node id** — if the user gave only a function name, discover with:
   ```bash
   .venv/bin/python -m pytest --collect-only -q 2>/dev/null | grep -F '::TEST_NAME'
   ```
   Prefer an exact function-name match. Ask once if multiple nodes match.

5. **Demo flag** — if the node is under `tests/test_*_pomhealer.py` or the test has `@pytest.mark.pomhealer_demo`, add `--run-pomhealer-demo`. Headed / slow-mo only via env (`POMHEALER_DEMO_HEADLESS`, `POMHEALER_DEMO_SLOW_MO`) — do not invent CLI flags.

6. **Run** (example):
   ```bash
   .venv/bin/python -m pytest tests/test_saucedemo_pomhealer.py::test_saucedemo_broken_login_button --run-pomhealer-demo -v
   ```

7. **Report** — exit status; on failure, surface any new `pomhealer-artifacts/failures/F-*.json` / `.md` / screenshot and next steps (`/pomhealer-propose` or `/pomhealer-review`). Do not auto-propose unless the user asks.

## Rules

- Do not edit `pages/*.py` or apply patches.
- Do not skip tests or weaken assertions to force green.
- Prefer project defaults for browser selection unless the user asks otherwise.
