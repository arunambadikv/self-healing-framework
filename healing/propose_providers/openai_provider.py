"""OpenAI + Playwright MCP propose provider."""

from __future__ import annotations

from pathlib import Path

from healing.llm_config import LlmConfig
from healing.propose_providers.mcp_tool_loop import openai_tool_loop, run_async


class OpenAIProposeProvider:
    def run_propose(
        self,
        prompt: str,
        *,
        workspace: Path,
        config: LlmConfig,
        storage_state: Path | None = None,
    ) -> str:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "openai package required — pip install 'healing[openai]' or 'healing[propose]'"
            ) from exc
        try:
            import mcp  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "mcp package required — pip install 'healing[openai]' or 'healing[propose]'"
            ) from exc

        return run_async(
            openai_tool_loop(
                prompt=prompt,
                workspace=workspace,
                api_key=config.api_key,
                model=config.model,
                storage_state=storage_state,
            )
        )
