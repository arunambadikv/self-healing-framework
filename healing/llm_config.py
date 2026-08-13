"""Resolve LLM provider, API key, and model for MCP propose."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROVIDERS = frozenset({"cursor", "openai", "anthropic"})

DEFAULT_MODELS = {
    "cursor": "composer-2.5",
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-4-5",
}

KEY_ENV_VARS = {
    "cursor": "CURSOR_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key: str
    model: str
    key_env: str

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class LlmConfigError(ValueError):
    """Raised when provider/key configuration is invalid."""


def normalize_provider(raw: str | None) -> str:
    provider = (raw or "cursor").strip().lower() or "cursor"
    if provider not in PROVIDERS:
        raise LlmConfigError(
            f"Unknown HEALING_LLM_PROVIDER={raw!r}; expected one of: "
            + ", ".join(sorted(PROVIDERS))
        )
    return provider


def resolve_llm_config(*, require_key: bool = False) -> LlmConfig:
    """Read provider/key/model from environment (call after load_dotenv_files)."""
    provider = normalize_provider(os.environ.get("HEALING_LLM_PROVIDER"))
    key_env = KEY_ENV_VARS[provider]
    api_key = os.environ.get(key_env, "").strip()

    model = (
        os.environ.get("HEALING_LLM_MODEL", "").strip()
        or (os.environ.get("HEALING_MCP_MODEL", "").strip() if provider == "cursor" else "")
        or DEFAULT_MODELS[provider]
    )

    cfg = LlmConfig(provider=provider, api_key=api_key, model=model, key_env=key_env)
    if require_key and not cfg.has_key:
        raise LlmConfigError(
            f"{key_env} required for HEALING_LLM_PROVIDER={provider}. "
            f"Set it in .env or the environment (capture/review/apply still work without it)."
        )
    return cfg


def missing_key_message(cfg: LlmConfig) -> str:
    install = {
        "cursor": "pip install 'healing[mcp]'",
        "openai": "pip install 'healing[openai]'",
        "anthropic": "pip install 'healing[anthropic]'",
    }[cfg.provider]
    return (
        f"{cfg.key_env} required for MCP propose (HEALING_LLM_PROVIDER={cfg.provider}).\n"
        "  Capture/scan/stub/review/apply work without it.\n"
        f"  Install:  {install}  (or healing[propose] for all)\n"
        f"  Set key:  export {cfg.key_env}=...  (or put it in .env)\n"
        "  Check:    healing-doctor"
    )
