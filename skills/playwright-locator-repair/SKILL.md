---
name: playwright-locator-repair
description: repair broken Playwright Python locators and selector registries from pytest failures, Playwright traces, screenshots, accessibility snapshots, or healing reports. Use when asked to diagnose failing Playwright tests, update locator_registry.yaml, generate safer locators, or use Playwright MCP to inspect current UI and propose selector fixes.
---

# Playwright Locator Repair

## Objective

Repair broken Playwright Python selectors safely and minimally.

## Workflow

1. Read the failing test output, healing report, locator registry, and relevant page/test files.
2. Determine whether the failure is likely:
   - selector break
   - real product bug
   - timeout/performance issue
   - test data issue
   - changed user flow
3. If it is a selector break, inspect the current UI.
4. Prefer Playwright MCP accessibility snapshots when available.
5. Propose or apply the smallest safe update to `locator_registry.yaml`.

## Locator Priority

Always prefer locators in this order:

1. `get_by_test_id`
2. `get_by_role`
3. `get_by_label`
4. `get_by_text`
5. CSS selectors only as a last resort

Avoid XPath unless explicitly required.

## Rules

- Do not silently remove assertions.
- Do not weaken assertions to make tests pass.
- Do not replace meaningful checks with generic visibility checks.
- Do not add arbitrary sleeps.
- Do not use brittle CSS if a semantic locator is available.
- Do not auto-heal destructive, payment, deletion, or permission-changing actions without review.
- Keep updates limited to locator registry or page object files unless instructed otherwise.
- Always explain what changed and why.

## Output Format

When proposing a repair, return:

```json
{
  "classification": "selector_break | product_bug | timeout | test_data | changed_flow | unknown",
  "semantic_key": "...",
  "old_locator": "...",
  "new_locator": "...",
  "confidence": 0.0,
  "files_to_update": ["locator_registry.yaml"],
  "reason": "...",
  "patch": "..."
}
```

## Validation

After updating a locator:

1. Run the specific failing test.
2. Confirm the original user journey still happens.
3. Confirm assertions are unchanged.
4. Confirm healing report has no failed event for that key.

## Related Skills

Use these companion skills when the task is more specific:

- `playwright-registry-update`: use when the main task is updating `locator_registry.yaml`, promoting fallback locators, adding fallback selectors, or cleaning registry entries.
- `playwright-locator-patching`: use when the main task is generating or applying code patches for broken locators, framework files, page objects, or tests.

Default routing:

1. Diagnose failure first with `playwright-locator-repair`.
2. Update registry with `playwright-registry-update`.
3. Generate/apply code diff with `playwright-locator-patching`.
