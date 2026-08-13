"""Propose provider interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from healing.llm_config import LlmConfig


class ProposeProvider(Protocol):
    def run_propose(
        self,
        prompt: str,
        *,
        workspace: Path,
        config: LlmConfig,
        storage_state: Path | None = None,
    ) -> str:
        """Run agent + Playwright MCP; return a short summary string."""
        ...
