"""Propose provider package."""

from __future__ import annotations

from pomhealer.llm_config import OPENAI_COMPAT_PROVIDERS, LlmConfig
from pomhealer.propose_providers.base import ProposeProvider


def get_provider(config: LlmConfig) -> ProposeProvider:
    if config.provider == "cursor":
        from pomhealer.propose_providers.cursor_provider import CursorProposeProvider

        return CursorProposeProvider()
    if config.provider in OPENAI_COMPAT_PROVIDERS:
        from pomhealer.propose_providers.openai_provider import OpenAICompatProposeProvider

        return OpenAICompatProposeProvider()
    raise ValueError(f"Unsupported provider: {config.provider}")
