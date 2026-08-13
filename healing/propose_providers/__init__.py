"""Propose provider package."""

from __future__ import annotations

from healing.llm_config import LlmConfig
from healing.propose_providers.base import ProposeProvider


def get_provider(config: LlmConfig) -> ProposeProvider:
    if config.provider == "cursor":
        from healing.propose_providers.cursor_provider import CursorProposeProvider

        return CursorProposeProvider()
    if config.provider == "openai":
        from healing.propose_providers.openai_provider import OpenAIProposeProvider

        return OpenAIProposeProvider()
    if config.provider == "anthropic":
        from healing.propose_providers.anthropic_provider import AnthropicProposeProvider

        return AnthropicProposeProvider()
    raise ValueError(f"Unsupported provider: {config.provider}")
