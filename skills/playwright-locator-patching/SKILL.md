---
name: playwright-locator-patching
description: generate and apply safe patches for broken Playwright Python locators, SmartPage semantic-key tests, locator registries, and page object files. Use when asked to create diffs, patch stale selectors, repair locator failures, apply healing report recommendations, or update Playwright Python test framework files without weakening assertions.
---

# Playwright Locator Patching

## Objective

Generate safe, minimal patches for broken Playwright Python locators and selector registry entries.

Patches should preserve test intent and only change what is necessary.

## Inputs

Use available context:

- pytest failure output
- healing report JSON
- patch suggestion Markdown
- `locator_registry.yaml`
- Playwright Python tests
- `SmartPage` wrapper code
- page objects, if present
- Playwright MCP accessibility snapshots

## Patch Workflow

1. Identify the failing semantic key or raw locator.
2. Classify the failure:
   - selector break
   - app regression
   - timeout
   - test data issue
   - changed flow
   - framework bug
3. If the issue is a selector break, find the most stable replacement locator.
4. Prefer updating `locator_registry.yaml`.
5. Update test files only when:
   - the semantic key is wrong
   - the test used raw Playwright selectors directly
   - the framework API needs to support the required action
6. Generate a focused patch.
7. Include a validation command.

## Patch Priority

Patch files in this order:

1. `locator_registry.yaml`
2. page object file, if the project uses page objects
3. `healing/locator_builder.py`, only if a missing locator type is needed
4. `healing/smart_page.py`, only if a missing framework action is needed
5. test files, only if test intent or semantic key usage is wrong

## Locator Priority

Prefer:

```text
test_id → role → label → placeholder → text → css
```

Avoid XPath.

Avoid brittle positional selectors such as:

```python
page.locator("button").nth(3)
```

unless there is no stable alternative and the reason is documented.

## Patch Rules

Allowed:

* promote a successful fallback to preferred
* add a new fallback locator
* replace stale button text with current accessible name
* add support for a missing locator type
* replace raw selectors in tests with semantic SmartPage keys
* add clear error messages

Not allowed:

* remove assertions
* weaken assertions
* skip tests to make CI green
* add arbitrary sleeps
* replace user-flow checks with generic visibility checks
* patch unrelated files
* silently change test behavior

## Example Patch: Promote Fallback

Before:

```yaml
demo.green_button:
  intent: "click the green demo button"
  action: "click"
  preferred:
    - type: role
      role: "button"
      name: "Old Button Name"
  fallback:
    - type: role
      role: "button"
      name: "Click Me (Green)"
```

After:

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
```

## Example Patch: Replace Raw Selector in Test

Before:

```python
page.locator("#myTextInput").fill("hello")
```

After:

```python
smart.fill("demo.text_input", "hello")
```

Add or update registry:

```yaml
demo.text_input:
  intent: "fill the main demo text input"
  action: "fill"
  preferred:
    - type: css
      value: "#myTextInput"
  fallback:
    - type: label
      value: "Text Input Field:"
```

If the label locator works, prefer the label locator instead of CSS.

## Output Format

Return:

```json
{
  "classification": "selector_break | app_regression | timeout | test_data | changed_flow | framework_bug | unknown",
  "patch_type": "registry_only | page_object | framework | test_refactor | no_patch",
  "semantic_key": "...",
  "confidence": 0.0,
  "reason": "...",
  "files_changed": ["locator_registry.yaml"],
  "validation_command": "pytest tests/test_demo_buttons_links.py -q",
  "patch": "..."
}
```

## Validation

Every patch must include a validation command.

Examples:

```bash
pytest tests/test_demo_buttons_links.py -q
pytest tests/test_demo_text_inputs.py::test_text_input -q
pytest -q
```

After validation, check:

1. The affected test passes.
2. No assertions were weakened.
3. Healing report does not contain unexpected failures.
4. The patch is limited to the relevant files.
5. The locator is not overly broad.
