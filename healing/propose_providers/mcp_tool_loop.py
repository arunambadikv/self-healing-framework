"""Shared MCP stdio session + tool-calling helpers for OpenAI/Anthropic loops."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from healing.mcp_stdio import McpStdioConfig, load_playwright_mcp_stdio

MAX_TOOL_STEPS = 40


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


def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", None) or tool.name,
                    "parameters": schema,
                },
            }
        )
    return out


def mcp_tools_to_anthropic(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        out.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", None) or tool.name,
                "input_schema": schema,
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
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    async with playwright_mcp_session(workspace, storage_state=storage_state) as (session, tools):
        openai_tools = mcp_tools_to_openai(tools)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a Playwright POM healing agent. Use browser tools to verify "
                    "locators, then edit the patch JSON/MD files on disk as instructed. "
                    "Do not modify pages/*.py."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        last_text = ""
        for _ in range(max_steps):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools or None,
            )
            choice = response.choices[0].message
            tool_calls = choice.tool_calls or []
            if not tool_calls:
                last_text = (choice.content or "").strip()
                return last_text or "done"

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result = await call_mcp_tool(session, tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result[:12000],
                    }
                )
        return last_text or "max tool steps reached"


async def anthropic_tool_loop(
    *,
    prompt: str,
    workspace: Path,
    api_key: str,
    model: str,
    storage_state: Path | None,
    max_steps: int = MAX_TOOL_STEPS,
) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    async with playwright_mcp_session(workspace, storage_state=storage_state) as (session, tools):
        anthropic_tools = mcp_tools_to_anthropic(tools)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        system = (
            "You are a Playwright POM healing agent. Use browser tools to verify "
            "locators, then edit the patch JSON/MD files on disk as instructed. "
            "Do not modify pages/*.py."
        )
        last_text = ""
        for _ in range(max_steps):
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system,
                tools=anthropic_tools or None,
                messages=messages,
            )
            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]
            if text_blocks:
                last_text = "\n".join(getattr(b, "text", "") for b in text_blocks).strip()

            if response.stop_reason == "end_turn" or not tool_uses:
                return last_text or "done"

            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in tool_uses:
                name = block.name
                args = dict(block.input or {})
                tool_result = await call_mcp_tool(session, name, args)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result[:12000],
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        return last_text or "max tool steps reached"
