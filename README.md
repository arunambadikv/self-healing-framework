# Playwright Python Self-Healing Framework

A reusable Playwright Python self-healing selector framework. Tests use semantic action keys instead of hardcoded selectors. When a preferred locator fails, the framework tries fallback locators in deterministic order, records healing events, and generates reviewable patch suggestions — without silently weakening assertions or rewriting test code during CI.

The first validation target is the [SeleniumBase demo page](https://seleniumbase.io/demo_page).

For a consolidated team status (completed work, advantages, limitations, MCP/agent roadmap), see [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Branch policy

Repository: [arunambadikv/self-healing-framework](https://github.com/arunambadikv/self-healing-framework)

```bash
git clone https://github.com/arunambadikv/self-healing-framework.git
cd self-healing-framework
git checkout dev    # day-to-day work and future auto-healing
```

| Branch | Purpose |
|--------|---------|
| **`dev`** | Default integration branch: tests, registry edits, MCP/agent repair, and (when enabled) automated healing commits. Push here freely. |
| **`main`** | Stable, reviewed line. Changes land only via pull request after CI passes. |

### GitHub protection for `main`

Configure once in the repo: **Settings → Branches → Add rule** (branch name pattern: `main`).

1. **Require a pull request before merging** — blocks direct pushes to `main`. Promote work with `dev` → `main` PRs ([open PR](https://github.com/arunambadikv/self-healing-framework/compare/main...dev)).
2. **Require status checks to pass before merging** — select the check that appears after at least one PR has run Actions (see below).
3. **Require branches to be up to date before merging** (recommended) — the PR must include the latest `main` so CI ran on the real merge result.

Optional but useful: **Dismiss stale pull request approvals when new commits are pushed**, **Require conversation resolution before merging**, and **Include administrators** so admins follow the same rules.

**Do not** add the same strict protection to **`dev`** while automated healing may push commits there without a PR.

### Required status check (CI on PRs to `main`)

Workflow: **Healing Framework CI** (`.github/workflows/healing-ci.yml`), job: **`test-and-gates`**.

GitHub may show the required check as `test-and-gates` or `Healing Framework CI / test-and-gates`. If the list is empty, open any PR into `main`, wait for Actions to finish, then return to the branch rule and select that check.

That job runs:

- `pytest tests/ -q`
- `python -m healing.registry_lint`
- `python -m healing.ci_gates`

MCP repair bundle generation in the same workflow uses `continue-on-error: true` and does not block merge.

### Typical workflow

```text
feature/fix on dev → push origin/dev → PR dev → main → CI green → merge
```

Local verification before opening a PR:

```bash
pytest tests/ -q
python -m healing.registry_lint
python -m healing.ci_gates
```

Future **dev-only** auto-healing (bot commits on `dev`, not on `main`) will use a separate workflow; `main` stays PR + human review only.

## Running Tests

Run all tests:

```bash
pytest
```

Run in headed mode:

```bash
pytest --headed
```

Run a specific test file:

```bash
pytest tests/test_demo_text_inputs.py --headed
```

## How the Locator Registry Works

`locator_registry.yaml` is the source of truth for semantic locators. Tests never hardcode selectors — they call stable keys through `SmartPage`:

```python
smart.fill("demo.text_input", "Hello")
smart.click("demo.green_button")
smart.select_option("demo.select_dropdown", "75%")
smart.expect_visible("demo.green_text")
```

Each registry entry defines:

- **intent** — human-readable purpose
- **action** — expected interaction (`click`, `fill`, `check`, etc.)
- **preferred** — primary locator candidates tried first
- **fallback** — secondary candidates tried if preferred fails

Example:

```yaml
demo.green_button:
  intent: "click the green demo button"
  action: "click"
  preferred:
    - type: role
      role: "button"
      name: "Click Me (Green)"
  fallback:
    - type: text
      value: "Click Me (Green)"
    - type: css
      value: "#myButton"
```

Supported locator types: `test_id`, `role`, `label`, `text`, `placeholder`, `css`, `frame_css`.

Locator priority when creating or repairing entries:

```text
test_id → role → label → placeholder → text → css
```

## How Runtime Healing Works

1. `SmartPage` loads candidates for a semantic key from the registry.
2. It tries `preferred` locators first, then `fallback` locators.
3. If a fallback succeeds, the test continues and the event is recorded as `healed`.
4. If all candidates fail, a detailed `AllLocatorCandidatesFailedError` is raised.
5. After each test, a JSON healing report and Markdown patch suggestion are written.

```text
test uses semantic key
→ preferred locator fails
→ fallback locator works
→ test continues
→ healing event recorded
→ registry patch suggestion generated
```

The framework does **not** call LLMs mid-test, weaken assertions, or rewrite test files during normal execution.

## Reading Healing Reports

JSON reports are saved to `artifacts/healing-reports/<test_name>.json`:

```json
{
  "events": [
    {
      "key": "demo.green_button",
      "action": "click",
      "status": "healed",
      "used_candidate": {
        "type": "role",
        "role": "button",
        "name": "Click Me (Green)"
      },
      "message": "demo.green_button succeeded using healed locator"
    }
  ],
  "summary": {
    "total": 1,
    "primary": 0,
    "healed": 1,
    "failed": 0
  }
}
```

Event statuses: `primary` (preferred worked), `healed` (fallback worked), `failed` (all candidates failed or missing key).

When a test uses a semantic key that does not exist in `locator_registry.yaml`, the framework:

1. records a `failed` event with `details.classification = "missing_key"`
2. includes a suggested YAML stub entry in `details.suggested_registry_entry`
3. generates a Markdown patch suggestion for reviewer action

This is suggestion-only; it does not write to the registry automatically.

## Generating Patch Suggestions

Patch suggestions are generated automatically after each test to `artifacts/patch-suggestions/<test_name>.md`.

You can also generate them manually:

```python
from healing.patcher import generate_registry_patch_markdown

generate_registry_patch_markdown(
    "artifacts/healing-reports/test_buttons_links[chromium].json",
    "artifacts/patch-suggestions/test_buttons_links.md",
)
```

Or from the command line:

```bash
python -c "
from healing.patcher import generate_registry_patch_markdown
generate_registry_patch_markdown(
    'artifacts/healing-reports/test_buttons_links[chromium].json',
    'artifacts/patch-suggestions/test_buttons_links.md',
)
"
```

Patch suggestions are **review-only**. The framework does not auto-edit `locator_registry.yaml`.
Reviewers copy or apply suggested entries manually.

### Optional: apply one reviewed suggestion via CLI

Use the helper command below to apply one suggestion in a controlled way.
It is dry-run by default and only writes when `--apply` is passed.

```bash
python -m healing.apply_suggestion \
  --report artifacts/healing-reports/test_buttons_links[chromium].json \
  --key demo.green_button \
  --change-type promote_fallback
```

Write to registry after review:

```bash
python -m healing.apply_suggestion \
  --report artifacts/healing-reports/test_buttons_links[chromium].json \
  --key demo.green_button \
  --change-type promote_fallback \
  --apply
```

For missing keys (suggested stub entries), use:

```bash
python -m healing.apply_suggestion \
  --report artifacts/healing-reports/missing-key-smoke.json \
  --key demo.non_existent_key \
  --change-type add_semantic_key
```

## Phase A — CI Gates

Run after tests to enforce registry quality, smart test policy, and healing thresholds.

```bash
pytest tests/ -q
python -m healing.registry_lint
python -m healing.ci_gates
# or
bash scripts/run_ci_gates.sh
```

Configure thresholds in `healing/ci_gates_config.yaml`:

- `max_failed_events` — fail if any healing event has `failed` status
- `max_healed_ratio_warn` / `max_healed_ratio_fail` — warn/fail on fallback usage rate
- `test_policy.allowlist` — exempt specific test files from smart-only policy

Lint-only (skip report thresholds):

```bash
python -m healing.ci_gates --skip-reports
```

## Phase B — MCP-Assisted Repair (Cursor + Playwright MCP)

Playwright MCP is integrated for locator repair. Cursor should have MCP connected (see `.cursor/mcp.json` and `AGENTS.md`).

### Full workflow

```bash
bash scripts/repair_with_mcp.sh
```

Or step by step:

```bash
pytest tests/ -q
python -m healing.mcp_repair_pipeline
```

### Repair in Cursor Agent

1. Open `artifacts/mcp-repair-bundles/prompts/<key>__<trigger>.md`
2. Ask Cursor Agent to run Playwright MCP (`browser_navigate`, `browser_snapshot`)
3. Agent writes `artifacts/mcp-repair-bundles/resolved/<key>.json`
4. Apply:

```bash
python -m healing.mcp_apply --key demo.green_button --apply
pytest tests/ -q
```

### Outputs

| Path | Purpose |
|------|---------|
| `prompts/*.md` | Cursor agent task with MCP CallMcpTool steps |
| `mcp-plans/*.json` | Structured MCP tool arguments |
| `proposals/*.json` | Draft LocatorPatchResult |
| `resolved/*.json` | Agent output after MCP inspection (you create via review) |

### Auto-generate bundles after tests (optional)

After pytest (smart tests with healed/failed events, or raw-learning tests):

```bash
pytest tests/ -q
# MCP prompts: artifacts/mcp-repair-bundles/prompts/
# Agent repair → artifacts/mcp-repair-bundles/resolved/*.json
bash scripts/apply_mcp_resolved.sh
```

Optional: `HEALING_MCP_AUTO=0` disables post-test MCP for smart tests; `HEALING_RAW_MCP=0` disables raw-learning MCP.

### Local Playwright probe (without Cursor MCP)

```bash
python -m healing.mcp_repair_pipeline --inspect
```

## Runtime-Assisted Agent Runner (Suggestion-Only)

You can generate AI-ready prompt bundles from new healing reports without mutating the registry.

This runner:

- reads new/updated JSON reports from `artifacts/healing-reports/`
- routes each case to the appropriate skills
  - `playwright-registry-update` (+ `playwright-locator-patching`) for `promote_fallback` and `add_semantic_key`
  - `playwright-locator-repair` (+ companions) for unresolved failed events
- writes prompt files to `artifacts/agent-prompts/`
- writes patch proposal JSON to `artifacts/agent-proposals/`
- tracks processed reports in `artifacts/agent-proposals/.agent-runner-state.json`

Run only new/changed reports:

```bash
python -m healing.agent_runner
```

Rebuild proposals for all reports:

```bash
python -m healing.agent_runner --all
```

This is still review-only: no direct update is made to `locator_registry.yaml`.
Use `python -m healing.apply_suggestion ... --apply` after review.

## Convert Raw Tests to SmartPage

Use the converter to migrate common raw Playwright lines to `smart.*` calls.
It uses locator candidates from `locator_registry.yaml` to map lines to semantic keys.

**Scan all policy-violating tests** (same rules as `healing.ci_gates` test_policy):

```bash
python -m healing.convert_to_smart --scan-tests          # dry-run
python -m healing.convert_to_smart --scan-tests --apply  # write files
```

Single file:

```bash
python -m healing.convert_to_smart --file tests/test_example_raw.py
python -m healing.convert_to_smart --file tests/test_example_raw.py --apply
```

**Auto-convert before pytest** (dev workflow; not enabled in CI):

```bash
bash scripts/setup_smart_test_conversion.sh   # writes .env.healing
source .env.healing
pytest                                        # converts raw files, then runs tests

# or one flag / wrapper:
pytest --healing-auto-convert
./scripts/run_pytest_with_auto_convert.sh
```

Notes:

- Supports common patterns (locator click/fill/check/uncheck, get_by_text, get_by_role+name with optional `exact=True`, get_by_placeholder, visible expectations).
- Adds the `smart` fixture to test signatures when missing; drops unused `playwright.sync_api` imports after conversion.
- Ambiguous or unmapped lines are left with a `# TODO(convert_to_smart): ...` comment for manual review.

## Registry Updates and Locator Patching

This framework separates runtime healing from long-term maintenance.

**Runtime healing:**

```text
preferred locator fails
→ fallback locator works
→ test continues
→ healing event recorded
```

**Registry update:**

```text
healing report reviewed
→ successful fallback is evaluated
→ patch suggestion generated
→ reviewer promotes stable locator
```

**Locator patching:**

```text
selector failure diagnosed
→ registry/page object/test patch generated
→ affected test is rerun
→ patch is reviewed
```

The framework does not silently rewrite tests during CI. All registry updates and locator patches should be reviewable.

See companion skills in `skills/` for agent-assisted repair workflows.

## Cursor + Playwright MCP for Repair

Use MCP for inspection and diagnosis, not silent CI mutation.

Suggested Cursor MCP command:

```bash
npx @playwright/mcp@latest
```

Optional headless mode:

```bash
npx @playwright/mcp@latest --headless
```

**Use MCP for:**

- page inspection
- accessibility snapshot
- locator recommendations
- repair diagnosis
- patch suggestions

**Do not use MCP for:**

- silent CI mutation
- assertion weakening
- bypassing user flows
- rewriting tests until green

Generate a repair prompt for a failed key:

```python
from healing.agent_repair_stub import generate_mcp_repair_prompt

prompt = generate_mcp_repair_prompt(
    semantic_key="demo.green_button",
    action="click",
    intent="click the green demo button",
    base_url="https://seleniumbase.io/demo_page",
    last_error="timeout",
)
print(prompt)
```

## Safety Rules

- Never silently weaken assertions.
- Never silently rewrite test code during normal test execution.
- Fallback paths are strictly deterministic — no LLM calls mid-test.
- Registry updates are suggestion-only until a human reviews and applies them.
- Do not auto-heal destructive, payment, deletion, or permission-changing actions without review.

## Framework Limitations

- Healing only works for locators defined in the registry with fallback candidates.
- `drag_to` requires both source and target keys to resolve; drag/drop on public demo pages may be flaky.
- iframe locators depend on frame selectors remaining stable.
- Broad CSS fallbacks can match unintended elements — prefer semantic locators.
- The framework records healing events but does not automatically promote fallbacks to preferred.

## Extending to Another Application

1. Copy the `healing/` package and `locator_registry.yaml` structure.
2. Create a new registry with semantic keys for your app (e.g. `login.email`, `checkout.submit`).
3. Map each key to `preferred` and `fallback` locators using the priority order above.
4. Wire `SmartPage` in your `conftest.py` with your app's base URL.
5. Write tests using semantic keys only — no raw selectors in test files.
6. Review healing reports after runs and promote stable fallbacks via patch suggestions.
7. Use the skills in `skills/` when locators break and need agent-assisted repair.

## Project Structure

```text
playwright-healing-framework/
  README.md
  requirements.txt
  pytest.ini
  locator_registry.yaml
  healing/           # Core framework
  tests/             # SeleniumBase demo validation tests
  artifacts/
    healing-reports/
    patch-suggestions/
  skills/            # Cursor agent repair instructions
```

## Demo Test Coverage

Tests against `https://seleniumbase.io/demo_page` cover:

| Test file | Coverage |
|-----------|----------|
| `test_demo_text_inputs.py` | text input, textarea, prefilled, placeholder, readonly |
| `test_demo_buttons_links.py` | buttons, links, visibility (includes intentional healing demo) |
| `test_demo_dropdowns.py` | select dropdown, 25/50/75/100%, meter |
| `test_demo_checkboxes_radios.py` | radios, checkboxes, checkbox group |
| `test_demo_iframe.py` | iframe image, iframe checkbox |
| `test_demo_drag_drop.py` | drag/drop (optional/skipped — flaky on public page) |

The `demo.green_button` key intentionally has a broken preferred locator to demonstrate runtime healing.
