"""Shared Playwright MCP package pin for templates, doctor, and SDK runner."""

# Pin for reproducibility (replace @latest). Bump intentionally when upgrading MCP.
PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.79"
DEFAULT_MCP_MODEL = "composer-2.5"  # cursor default; see healing.llm_config.DEFAULT_MODELS
