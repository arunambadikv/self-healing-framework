"""Shared Playwright MCP stdio command/args (provider-agnostic)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pomhealer.mcp_constants import PLAYWRIGHT_MCP_PACKAGE


@dataclass
class McpStdioConfig:
    command: str = "npx"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def with_storage_state_args(args: list[str], storage_state: Path) -> list[str]:
    cleaned = [a for a in args if a != "--isolated" and not str(a).startswith("--storage-state")]
    cleaned.append("--isolated")
    cleaned.append(f"--storage-state={storage_state.resolve()}")
    return cleaned


def load_playwright_mcp_stdio(
    workspace: Path,
    *,
    storage_state: Path | None = None,
) -> McpStdioConfig:
    """Load Playwright MCP stdio config from .cursor/mcp.json or built-in pin."""
    command = "npx"
    args: list[str] = [PLAYWRIGHT_MCP_PACKAGE]
    env: dict[str, str] = {}

    mcp_path = workspace / ".cursor" / "mcp.json"
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}
        playwright = servers.get("playwright") or servers.get(
            "project-0-playwright-healing-framework-playwright"
        )
        if playwright and playwright.get("command"):
            command = playwright["command"]
            args = list(playwright.get("args") or [])
            env = dict(playwright.get("env") or {})

    if storage_state is not None:
        args = with_storage_state_args(args, storage_state)
        env = {
            **env,
            "PLAYWRIGHT_MCP_STORAGE_STATE": str(storage_state.resolve()),
        }

    return McpStdioConfig(command=command, args=args, env=env)
