"""OpenAI-compatible propose provider (OpenAI, Gemini, Groq)."""

from __future__ import annotations

from pathlib import Path

from healing.llm_config import LlmConfig
from healing.propose_providers.mcp_tool_loop import openai_tool_loop, run_async


class OpenAICompatProposeProvider:
    """Chat Completions + Playwright MCP via the OpenAI Python SDK."""

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
                "openai package missing — reinstall healing (openai ships with the package)"
            ) from exc
        try:
            import mcp  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "mcp package missing — reinstall healing (mcp ships with the package)"
            ) from exc

        return run_async(
            openai_tool_loop(
                prompt=prompt,
                workspace=workspace,
                api_key=config.api_key,
                model=config.model,
                storage_state=storage_state,
                base_url=config.openai_base_url,
            )
        )


# Back-compat alias
OpenAIProposeProvider = OpenAICompatProposeProvider
