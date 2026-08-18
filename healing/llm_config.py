"""Resolve LLM provider, API key, and model for MCP propose."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROVIDERS = frozenset({"cursor", "openai", "gemini", "groq"})

DEFAULT_MODELS = {
    "cursor": "composer-2.5",
    "openai": "gpt-4.1",
    "gemini": "gemini-3.6-flash",
    "groq": "openai/gpt-oss-120b",
}

KEY_ENV_VARS = {
    "cursor": "CURSOR_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}

# OpenAI-compatible chat APIs (cursor-sdk is used for provider=cursor).
OPENAI_COMPAT_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
}

OPENAI_COMPAT_PROVIDERS = frozenset(OPENAI_COMPAT_BASE_URLS)


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key: str
    model: str
    key_env: str
    openai_base_url: str | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class LlmConfigError(ValueError):
    """Raised when provider/key configuration is invalid."""


def normalize_provider(raw: str | None) -> str:
    provider = (raw or "cursor").strip().lower() or "cursor"
    if provider in {"google", "google-genai"}:
        provider = "gemini"
    if provider not in PROVIDERS:
        raise LlmConfigError(
            f"Unknown HEALING_LLM_PROVIDER={raw!r}; expected one of: "
            + ", ".join(sorted(PROVIDERS))
        )
    return provider


def _read_api_key(provider: str, key_env: str) -> str:
    key = os.environ.get(key_env, "").strip()
    if key:
        return key
    if provider == "gemini":
        return os.environ.get("GOOGLE_API_KEY", "").strip()
    return ""


def resolve_llm_config(*, require_key: bool = False) -> LlmConfig:
    """Read provider/key/model from environment (call after load_dotenv_files)."""
    provider = normalize_provider(os.environ.get("HEALING_LLM_PROVIDER"))
    key_env = KEY_ENV_VARS[provider]
    api_key = _read_api_key(provider, key_env)

    model = (
        os.environ.get("HEALING_LLM_MODEL", "").strip()
        or (os.environ.get("HEALING_MCP_MODEL", "").strip() if provider == "cursor" else "")
        or DEFAULT_MODELS[provider]
    )

    cfg = LlmConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        key_env=key_env,
        openai_base_url=OPENAI_COMPAT_BASE_URLS.get(provider),
    )
    if require_key and not cfg.has_key:
        raise LlmConfigError(
            f"{key_env} required for HEALING_LLM_PROVIDER={provider}. "
            f"Set it in .env or the environment (capture/review/apply still work without it)."
        )
    return cfg


def missing_key_message(cfg: LlmConfig) -> str:
    extra = ""
    if cfg.provider == "gemini":
        extra = "  Alternate: GOOGLE_API_KEY=... (used if GEMINI_API_KEY is empty)\n"
    return (
        f"{cfg.key_env} required for MCP propose (HEALING_LLM_PROVIDER={cfg.provider}).\n"
        "  Capture/scan/stub/review/apply work without it.\n"
        f"  Set key:  export {cfg.key_env}=...  (or put it in .env)\n"
        f"{extra}"
        "  Check:    healing-doctor"
    )
