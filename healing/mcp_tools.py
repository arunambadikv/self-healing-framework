from __future__ import annotations

import json
from typing import Any

# Cursor Playwright MCP server tool names (user-playwright).
MCP_SERVER_ID = "user-playwright"

MCP_REPAIR_TOOL_SEQUENCE = [
    "browser_navigate",
    "browser_snapshot",
    "browser_evaluate",
]

LOCATOR_PRIORITY = [
    "test_id",
    "role",
    "label",
    "placeholder",
    "text",
    "css",
]


def mcp_navigate(url: str) -> dict[str, Any]:
    return {
        "server": MCP_SERVER_ID,
        "tool": "browser_navigate",
        "arguments": {"url": url},
        "description": f"Open target page: {url}",
    }


def mcp_snapshot(*, depth: int | None = None, filename: str | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {}
    if depth is not None:
        args["depth"] = depth
    if filename:
        args["filename"] = filename
    return {
        "server": MCP_SERVER_ID,
        "tool": "browser_snapshot",
        "arguments": args,
        "description": "Capture accessibility snapshot to find stable locators.",
    }


def mcp_evaluate_probe(candidate: dict[str, Any]) -> dict[str, Any]:
    """Optional: verify a registry candidate resolves to exactly one visible element."""
    script = _candidate_probe_script(candidate)
    return {
        "server": MCP_SERVER_ID,
        "tool": "browser_evaluate",
        "arguments": {"function": script},
        "description": f"Probe candidate: {candidate}",
    }


def _candidate_probe_script(candidate: dict[str, Any]) -> str:
    ctype = candidate.get("type")
    if ctype == "css":
        sel = candidate.get("value", "")
        return (
            "() => {"
            f" const el = document.querySelector({json.dumps(sel)});"
            " return { count: el ? 1 : 0, visible: !!(el && el.offsetParent), tag: el?.tagName };"
            " }"
        )
    if ctype == "role":
        role = candidate.get("role", "")
        name = candidate.get("name", "")
        return (
            "() => {"
            f" const nodes = Array.from(document.querySelectorAll('[role=\"{role}\"], {json.dumps(role)}'));"
            f" const matches = nodes.filter(n => !{json.dumps(name)} || (n.getAttribute('aria-label')||n.textContent||'').includes({json.dumps(name)}));"
            " return { count: matches.length }; }"
        )
    return "() => ({ note: 'use browser_snapshot to propose locator manually' })"


def build_mcp_repair_plan(
    *,
    base_url: str,
    semantic_key: str,
    action: str,
    intent: str,
    registry_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Structured plan for Cursor agent using connected Playwright MCP."""
    steps = [
        mcp_navigate(base_url),
        mcp_snapshot(filename=f".playwright-mcp/repair-{semantic_key.replace('.', '_')}.yml"),
    ]
    if registry_entry:
        for candidate in list(registry_entry.get("preferred", [])) + list(
            registry_entry.get("fallback", [])
        ):
            if isinstance(candidate, dict) and candidate.get("type") == "css":
                steps.append(mcp_evaluate_probe(candidate))
                break

    return {
        "mcp_server": MCP_SERVER_ID,
        "semantic_key": semantic_key,
        "action": action,
        "intent": intent,
        "base_url": base_url,
        "locator_priority": LOCATOR_PRIORITY,
        "tool_sequence": MCP_REPAIR_TOOL_SEQUENCE,
        "steps": steps,
        "cursor_instructions": [
            "Use CallMcpTool with server 'user-playwright' for each step.",
            "Read skills: playwright-locator-repair, playwright-registry-update, playwright-locator-patching.",
            "Update locator_registry.yaml only unless instructed otherwise.",
            "Do not weaken assertions or rewrite tests to force green.",
            "Write resolved patch to artifacts/mcp-repair-bundles/resolved/<key>.json",
            "Human applies with: python -m healing.mcp_apply --key <key>",
        ],
    }
