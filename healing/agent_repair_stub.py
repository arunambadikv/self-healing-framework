from __future__ import annotations

import json
from typing import Any

from healing.mcp_tools import build_mcp_repair_plan, LOCATOR_PRIORITY


def generate_mcp_repair_prompt(
    *,
    semantic_key: str,
    action: str,
    intent: str,
    base_url: str,
    last_error: Exception | str | None = None,
    registry_entry: dict[str, Any] | None = None,
    trigger_type: str = "failed",
) -> str:
    plan = build_mcp_repair_plan(
        base_url=base_url,
        semantic_key=semantic_key,
        action=action,
        intent=intent,
        registry_entry=registry_entry,
    )
    error_text = str(last_error) if last_error else "n/a"

    return f"""# Playwright MCP Locator Repair (Cursor)

You have **Playwright MCP** connected (`{plan["mcp_server"]}`). Use it to inspect the live page and produce an accurate registry patch.

## Target
- semantic_key: `{semantic_key}`
- trigger_type: `{trigger_type}`
- action: `{action}`
- intent: {intent}
- base_url: `{base_url}`
- last_error: {error_text}

## Locator priority
```text
{" → ".join(LOCATOR_PRIORITY)}
```

## Required MCP tool calls (in order)

Use **CallMcpTool** for each step:

```json
{json.dumps(plan["steps"], indent=2)}
```

1. **browser_navigate** — open `{base_url}`
2. **browser_snapshot** — read accessibility tree; find the element matching intent
3. Optionally **browser_evaluate** — verify CSS candidate uniqueness

## Skills to follow
- `playwright-locator-repair` — diagnose
- `playwright-registry-update` — update `locator_registry.yaml`
- `playwright-locator-patching` — minimal patch + validation command

## Rules
- Do not weaken assertions.
- Do not bypass user flow or add arbitrary sleeps.
- Only update `locator_registry.yaml` unless instructed otherwise.
- Prefer semantic locators over broad CSS.

## Output files
1. Write resolved proposal JSON to:
   `artifacts/mcp-repair-bundles/resolved/{semantic_key.replace(".", "_")}.json`
2. Include `LocatorPatchResult` fields: classification, patch_type, semantic_key, confidence, reason, patch (YAML), validation_command

## Apply after review
```bash
python -m healing.mcp_apply --key {semantic_key} --apply
```
"""


def generate_mcp_repair_prompt_legacy(failed_key: str, last_error: Exception) -> str:
    """Backward-compatible wrapper."""
    return generate_mcp_repair_prompt(
        semantic_key=failed_key,
        action="unknown",
        intent=f"Repair locator for {failed_key}",
        base_url="https://seleniumbase.io/demo_page",
        last_error=last_error,
        trigger_type="failed",
    )
