"""Cursor SDK propose provider."""

from __future__ import annotations

from pathlib import Path

from pomhealer.llm_config import LlmConfig
from pomhealer.mcp_stdio import load_playwright_mcp_stdio


class CursorProposeProvider:
    def run_propose(
        self,
        prompt: str,
        *,
        workspace: Path,
        config: LlmConfig,
        storage_state: Path | None = None,
    ) -> str:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, StdioMcpServerConfig

        stdio = load_playwright_mcp_stdio(workspace, storage_state=storage_state)
        mcp_servers = {
            "playwright": StdioMcpServerConfig(
                command=stdio.command,
                args=stdio.args,
                env=stdio.env,
            )
        }
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=config.api_key,
                model=config.model,
                local=LocalAgentOptions(cwd=str(workspace)),
                mcp_servers=mcp_servers,
            ),
        )
        if result.status == "error":
            raise RuntimeError(f"SDK agent run failed: {result.result}")
        return str(result.result or "")
