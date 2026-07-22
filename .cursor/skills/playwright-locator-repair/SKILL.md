---
name: playwright-locator-repair
description: Repair broken Playwright locators in Page Object files from pytest failures, artifacts/failures/F-*.json reports, Playwright MCP snapshots, and healing-queue patches. Use when diagnosing failing POM tests, proposing fixes in pages/*.py, or writing P-*.json patch proposals with architecture_updates.
disable-model-invocation: true
---

# Playwright Locator Repair (POM)

## Objective

Repair broken Playwright locators in `pages/*.py` safely and minimally. Use with `/healing-propose` (MCP + proposals). Applying patches is `/healing-review` + `healing.pom_apply`.

## Workflow

1. Read `artifacts/failures/F-<id>.json` and `.md`, plus `artifacts/architecture/manifest.json`.
2. Classify the failure:
   - selector_break
   - app_regression
   - timeout
   - test_data
   - changed_flow
   - unknown
3. If selector_break: **Playwright MCP** — reach the failure UI, then `browser_snapshot`:
   - Prefer `artifacts.storage_state` from the failure JSON: MCP propose runner starts with
     `--isolated --storage-state=<path>`, then navigate to `environment.page_url`.
   - Fallback: `browser_set_storage_state` with that path, or replay successful `test_steps`
     before the failing step (correct locators from `pages/*.py`), then snapshot.
   - Do not only open `base_url` when `page_url` is a deeper authenticated page.
4. Propose locators from the live page (not guesses).
5. Write `artifacts/healing-queue/patches/P-<id>.json` with `architecture_updates` targeting **one property** in `pages/*.py`.
6. Promote to review queue (same as CLI after `mcp_propose_runner`):
   ```bash
   python -m healing.healing_review --promote P-<id>
   ```

## Locator priority

`test_id` → `role` → `label` → `placeholder` → `text` → `css` (last resort). Avoid XPath and brittle `.nth()` unless documented.

## Patch target

Update **locator properties** in page classes, e.g.:

```python
@property
def green_button(self) -> Locator:
    return self.page.get_by_role("button", name="Click Me (Green)")
```

Do not edit tests unless the page API or flow is wrong. Do not edit files outside `pages/` unless explicitly asked.

## Rules

- Do not remove or weaken assertions.
- Do not add arbitrary sleeps.
- Do not skip tests to force green.
- Do not auto-fix high-risk actions (iframe, navigation, destructive actions) without noting `risk_level: high`.

## Proposal JSON shape

```json
{
  "patch_id": "P-...",
  "failure_id": "F-...",
  "classification": "selector_break",
  "risk_level": "low | medium | high",
  "risk_reason": "...",
  "architecture_updates": [
    {
      "file": "pages/demo_page.py",
      "symbol": "green_button",
      "line": 42,
      "change_type": "replace_locator",
      "before": "return self.page.get_by_role(...)",
      "after": "return self.page.get_by_role(\"button\", name=\"Click Me (Green)\")"
    }
  ],
  "validation_command": "pytest tests/test_demo_buttons_links.py -q",
  "links": { "failure_json": "...", "failure_md": "..." }
}
```

Also write matching `P-<id>.md` for humans.

## Validation

Every proposal must include `validation_command` for the failing test file.
