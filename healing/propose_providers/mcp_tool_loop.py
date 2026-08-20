"""Shared MCP stdio session + OpenAI-compatible tool-calling helpers."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from healing.mcp_stdio import McpStdioConfig, load_playwright_mcp_stdio

MAX_TOOL_STEPS = 40
_RATE_LIMIT_RETRIES = 8
_INVALID_TOOL_RETRIES = 5
_TOOL_RESULT_CHARS = 4000
_RETRY_IN_SECONDS_RE = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)
_TOOL_NOT_IN_REQUEST_RE = re.compile(
    r"attempted to call tool '([^']+)' which was not in request\.tools"
)

# Playwright MCP exposes many large schemas; Groq free-tier TPM is 8k.
PROPOSE_MCP_TOOL_ALLOWLIST = frozenset(
    {
        "browser_navigate",
        "browser_navigate_back",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_wait_for",
        "browser_press_key",
        "browser_select_option",
        "browser_take_screenshot",
        "browser_handle_dialog",
    }
)

READ_FILE_PREFIXES = ("healer-artifacts/", "pages/", "tests/")
WRITE_FILE_PREFIXES = ("healer-artifacts/healing-queue/patches/",)
LOCAL_FILE_TOOL_NAMES = frozenset({"read_workspace_file", "write_workspace_file"})

WORKSPACE_FILE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": (
                "Read a UTF-8 file under pages/, tests/, or healer-artifacts/. "
                "Use this for patch JSON/MD and failure reports. "
                "Do not call browser_open_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative path",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_workspace_file",
            "description": (
                "Write UTF-8 content to healer-artifacts/healing-queue/patches/ only. "
                "Use this to complete P-*.json and P-*.md. Do not write pages/*.py."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative path under healing-queue/patches/",
                    },
                    "content": {"type": "string", "description": "Full file contents"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


@asynccontextmanager
async def playwright_mcp_session(
    workspace: Path,
    *,
    storage_state: Path | None = None,
) -> AsyncIterator[tuple[Any, list[Any]]]:
    """Yield (ClientSession, tools) connected to Playwright MCP over stdio."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cfg: McpStdioConfig = load_playwright_mcp_stdio(workspace, storage_state=storage_state)
    env = {**os.environ, **cfg.env}
    params = StdioServerParameters(command=cfg.command, args=cfg.args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            yield session, list(listed.tools or [])


def compact_json_schema(schema: Any, *, max_desc: int = 120) -> Any:
    """Drop verbose JSON-schema fields so Groq/Gemini requests stay under TPM caps."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"$schema", "additionalProperties", "$defs", "definitions"}:
            continue
        if key == "description" and isinstance(value, str):
            out[key] = value[:max_desc]
        elif key == "properties" and isinstance(value, dict):
            out[key] = {
                name: compact_json_schema(prop, max_desc=max_desc) for name, prop in value.items()
            }
        elif key in {"items", "anyOf", "oneOf", "allOf"}:
            if isinstance(value, list):
                out[key] = [compact_json_schema(item, max_desc=max_desc) for item in value]
            else:
                out[key] = compact_json_schema(value, max_desc=max_desc)
        else:
            out[key] = value
    return out


def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    selected = [tool for tool in tools if getattr(tool, "name", "") in PROPOSE_MCP_TOOL_ALLOWLIST]
    if not selected:
        selected = list(tools)
    out: list[dict[str, Any]] = []
    for tool in selected:
        schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        description = getattr(tool, "description", None) or tool.name
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": str(description)[:160],
                    "parameters": compact_json_schema(schema),
                },
            }
        )
    return out


async def call_mcp_tool(session: Any, name: str, arguments: dict[str, Any] | None) -> str:
    result = await session.call_tool(name, arguments or {})
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        else:
            parts.append(str(block))
    if getattr(result, "isError", False):
        return "ERROR: " + ("\n".join(parts) if parts else "tool failed")
    return "\n".join(parts) if parts else "(empty tool result)"


def openai_tool_call_payload(tc: Any) -> dict[str, Any]:
    """Serialize a tool call, keeping Gemini thought_signature extras.

    Gemini 3 OpenAI-compat requires extra_content.google.thought_signature on
    subsequent turns. Reconstructing only id/name/arguments causes HTTP 400.
    """
    if hasattr(tc, "model_dump"):
        dumped = tc.model_dump(exclude_none=True)
        payload: dict[str, Any] = {
            "id": dumped.get("id") or getattr(tc, "id", None),
            "type": dumped.get("type") or "function",
            "function": dumped.get("function")
            or {
                "name": tc.function.name,
                "arguments": tc.function.arguments or "{}",
            },
        }
        extra = dumped.get("extra_content")
        if extra:
            payload["extra_content"] = extra
        return payload
    payload = {
        "id": tc.id,
        "type": getattr(tc, "type", None) or "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments or "{}",
        },
    }
    extra = getattr(tc, "extra_content", None)
    if extra:
        payload["extra_content"] = extra
    return payload


def _workspace_rel(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def resolve_workspace_file_path(workspace: Path, raw: str, *, prefixes: tuple[str, ...]) -> Path:
    """Resolve a workspace-relative path and require it under allowed prefixes."""
    workspace = workspace.resolve()
    path = Path(str(raw).strip())
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.is_relative_to(workspace):
        raise ValueError(f"path escapes workspace: {raw}")
    rel = _workspace_rel(path, workspace)
    if not any(rel == p.rstrip("/") or rel.startswith(p) for p in prefixes):
        allowed = ", ".join(prefixes)
        raise ValueError(f"path {rel} is not under allowed prefixes: {allowed}")
    return path


def run_workspace_file_tool(workspace: Path, name: str, arguments: dict[str, Any]) -> str:
    raw_path = str(arguments.get("path") or "")
    try:
        if name == "read_workspace_file":
            path = resolve_workspace_file_path(workspace, raw_path, prefixes=READ_FILE_PREFIXES)
            if not path.is_file():
                return f"ERROR: file not found: {_workspace_rel(path, workspace)}"
            return path.read_text(encoding="utf-8")[:8000]
        if name == "write_workspace_file":
            path = resolve_workspace_file_path(workspace, raw_path, prefixes=WRITE_FILE_PREFIXES)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(arguments.get("content") or ""), encoding="utf-8")
            return f"wrote {_workspace_rel(path, workspace)}"
        return f"ERROR: unknown local tool {name}"
    except (OSError, ValueError) as exc:
        return f"ERROR: {exc}"


async def dispatch_tool(
    session: Any,
    workspace: Path,
    name: str,
    arguments: dict[str, Any] | None,
) -> str:
    args = arguments or {}
    if name in LOCAL_FILE_TOOL_NAMES:
        return run_workspace_file_tool(workspace, name, args)
    return await call_mcp_tool(session, name, args)


def invalid_tool_feedback(exc: BaseException, allowed: list[str] | None = None) -> str | None:
    """Return a short retry prompt when Groq rejects a tool name not in request.tools."""
    text = str(exc)
    match = _TOOL_NOT_IN_REQUEST_RE.search(text)
    if not match and "tool_use_failed" not in text and "not in request.tools" not in text:
        return None
    name = match.group(1) if match else "unknown"
    return (
        f"Tool `{name}` is not available. Only call tools from this request. "
        "For patch JSON/MD use read_workspace_file and write_workspace_file. "
        "For the live page use browser_navigate, browser_snapshot, browser_click, browser_type."
    )


def compact_chat_messages(messages: list[dict[str, Any]], *, tool_chars: int = 1500) -> list[dict[str, Any]]:
    """Shrink older tool payloads so a retry fits Groq's 8k TPM window."""
    compacted: list[dict[str, Any]] = []
    tool_indexes = [i for i, msg in enumerate(messages) if msg.get("role") == "tool"]
    keep_full = set(tool_indexes[-2:])
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool" and i not in keep_full:
            content = str(msg.get("content") or "")
            compacted.append({**msg, "content": content[:tool_chars]})
        else:
            compacted.append(msg)
    return compacted


def is_capacity_or_size_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (413, 429):
        return True
    text = str(exc).lower()
    return (
        "rate_limit" in text
        or "request too large" in text
        or "tokens per minute" in text
    )


def retry_delay_seconds(exc: BaseException, *, fallback: float) -> float:
    """Parse Gemini/OpenAI retry delay from a 429 error, else use fallback."""
    match = _RETRY_IN_SECONDS_RE.search(str(exc))
    if match:
        return max(fallback, float(match.group(1)) + 0.5)
    return fallback


def create_chat_completion_with_retry(client: Any, **kwargs: Any) -> Any:
    """Call chat.completions.create, waiting through free-tier 429/413 TPM limits."""
    from openai import APIStatusError, RateLimitError

    last_exc: BaseException | None = None
    for attempt in range(_RATE_LIMIT_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except (RateLimitError, APIStatusError) as exc:
            if not isinstance(exc, RateLimitError) and not is_capacity_or_size_error(exc):
                raise
            last_exc = exc
            if getattr(exc, "status_code", None) == 413 or "request too large" in str(exc).lower():
                messages = kwargs.get("messages")
                if isinstance(messages, list):
                    kwargs["messages"] = compact_chat_messages(messages)
                print("[healing] Request too large; compacted history...")
            delay = retry_delay_seconds(exc, fallback=25 + attempt * 10)
            print(f"[healing] Rate limited; retrying in {delay:.0f}s...")
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def run_async(coro):
    """Run async propose loop from sync CLI (safe when no running loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Nested event loop (rare in pytest); use a fresh loop in a thread if needed
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def openai_tool_loop(
    *,
    prompt: str,
    workspace: Path,
    api_key: str,
    model: str,
    storage_state: Path | None,
    max_steps: int = MAX_TOOL_STEPS,
    base_url: str | None = None,
) -> str:
    from openai import OpenAI

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    async with playwright_mcp_session(workspace, storage_state=storage_state) as (session, tools):
        openai_tools = mcp_tools_to_openai(tools) + WORKSPACE_FILE_TOOLS
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a Playwright POM healing agent. "
                    "Only call tools listed in this request — never invent names "
                    "(for example browser_open_file is not available). "
                    "Use Playwright browser_* tools to verify locators. "
                    "Use read_workspace_file and write_workspace_file to update "
                    "healer-artifacts/healing-queue/patches/*.json and *.md. "
                    "Do not modify pages/*.py."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        last_text = ""
        invalid_tool_attempts = 0
        from openai import BadRequestError

        for _ in range(max_steps):
            try:
                response = create_chat_completion_with_retry(
                    client,
                    model=model,
                    messages=messages,
                    tools=openai_tools or None,
                )
            except BadRequestError as exc:
                feedback = invalid_tool_feedback(exc)
                if not feedback or invalid_tool_attempts >= _INVALID_TOOL_RETRIES:
                    raise
                invalid_tool_attempts += 1
                print("[healing] Model called an unknown tool; retrying with a correction...")
                messages.append({"role": "user", "content": feedback})
                continue
            choice = response.choices[0].message
            tool_calls = choice.tool_calls or []
            if not tool_calls:
                last_text = (choice.content or "").strip()
                return last_text or "done"

            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [openai_tool_call_payload(tc) for tc in tool_calls],
            }
            extra = getattr(choice, "extra_content", None)
            if extra:
                assistant["extra_content"] = extra
            messages.append(assistant)
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result = await dispatch_tool(session, workspace, tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result[:_TOOL_RESULT_CHARS],
                    }
                )
        return last_text or "max tool steps reached"
