---
name: playwright-registry-update
description: update Playwright Python locator_registry.yaml files from healing reports, successful fallback locators, pytest failures, accessibility snapshots, or agent repair suggestions. Use when asked to promote fallback locators, add new locator candidates, clean stale selectors, reorganize registry entries, or keep semantic locator keys stable while improving selector reliability.
---

# Playwright Registry Update

## Objective

Update `locator_registry.yaml` safely and minimally without weakening tests or changing test intent.

The registry is the source of truth for semantic locator keys. Tests should continue to call stable semantic keys such as:

```python
smart.click("demo.green_button")
smart.fill("demo.text_input", "hello")
```

Do not force test files to change unless the semantic intent itself changed.

## Inputs

Use any available inputs:

* `locator_registry.yaml`
* healing JSON reports
* Markdown patch suggestions
* pytest failure output
* Playwright trace or screenshot notes
* Playwright MCP accessibility snapshot
* existing test files
* page object files, if present

## Registry Update Workflow

1. Read the current `locator_registry.yaml`.
2. Read the healing report or failed selector context.
3. Identify the semantic key involved.
4. Determine whether the issue is:

   * stale preferred locator
   * missing fallback locator
   * duplicate/ambiguous locator
   * changed UI semantics
   * real product bug
   * invalid test intent
5. If a fallback locator worked successfully, consider promoting it into `preferred`.
6. Keep the old preferred locator only if it is still useful across supported UI versions.
7. Add fallback locators only when they represent the same semantic intent.
8. Preserve semantic key names unless there is a clear reason to rename them.
9. Return a patch and explanation.

## Locator Priority

Prefer locators in this order:

1. `test_id`
2. `role`
3. `label`
4. `placeholder`
5. `text`
6. `css`

Avoid XPath unless explicitly required.

## Safe Promotion Rules

A fallback locator may be promoted to `preferred` only when:

* it successfully interacted with the intended element
* the post-action assertion passed
* it matches the same semantic intent
* it is not overly broad
* it is more stable or more semantic than the broken selector

Example: promote this:

```yaml
fallback:
  - type: role
    role: "button"
    name: "Click Me (Green)"
```

to:

```yaml
preferred:
  - type: role
    role: "button"
    name: "Click Me (Green)"
```

Do not promote this unless no better locator exists:

```yaml
fallback:
  - type: css
    value: "button"
```

because it is too broad.

## Registry Entry Format

Maintain this structure:

```yaml
semantic.key:
  intent: "clear human-readable intent"
  action: "click | fill | check | uncheck | select_option | expect_visible | expect_text | drag_to"
  preferred:
    - type: role
      role: "button"
      name: "Example"
  fallback:
    - type: text
      value: "Example"
    - type: css
      value: "button.example"
```

## Do Not

* Do not remove assertions from tests.
* Do not change semantic keys unnecessarily.
* Do not replace specific locators with broad CSS unless no better option exists.
* Do not delete fallback locators unless they are clearly wrong or harmful.
* Do not hide product bugs as selector updates.
* Do not update unrelated registry entries.
* Do not use arbitrary sleeps as a fix.

## Output Format

Return:

```json
{
  "classification": "registry_update",
  "semantic_key": "demo.green_button",
  "change_type": "promote_fallback | add_fallback | replace_stale | cleanup | no_change",
  "confidence": 0.0,
  "reason": "...",
  "files_to_update": ["locator_registry.yaml"],
  "patch": "..."
}
```

## Validation Checklist

After updating the registry:

1. Run the affected test only.
2. Confirm the test still validates the same user behavior.
3. Confirm assertions were not weakened.
4. Confirm the healing report no longer shows failure for the key.
5. Confirm broad CSS is not preferred when a semantic locator is available.
