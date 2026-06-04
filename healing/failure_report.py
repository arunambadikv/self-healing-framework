"""Capture and persist detailed pytest failure reports (F-*.json / F-*.md)."""

from __future__ import annotations

import json
import re
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healing.paths import FAILURES_DIR, ensure_queue_dirs
from healing.healing_queue import register_failure
from healing.step_trace import StepTraceCollector


def new_failure_id() -> str:
    return f"F-{uuid.uuid4().hex[:12]}"


def _parse_playwright_hint(exc_repr: str) -> dict[str, Any] | None:
    hint: dict[str, Any] = {}
    if "Locator" in exc_repr or "get_by_" in exc_repr or "locator(" in exc_repr:
        hint["kind"] = "locator"
    for pattern in (
        r"get_by_role\([^)]+\)",
        r"get_by_text\([^)]+\)",
        r"locator\([^)]+\)",
        r"get_by_placeholder\([^)]+\)",
    ):
        match = re.search(pattern, exc_repr)
        if match:
            hint["expression"] = match.group(0)
            break
    return hint or None


def _infer_failing_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not steps:
        return None
    return steps[-1]


def build_failure_payload(
    *,
    failure_id: str,
    test_nodeid: str,
    test_file: str,
    test_name: str,
    base_url: str,
    page_url: str | None,
    exception_type: str,
    exception_message: str,
    traceback_text: str,
    step_trace: StepTraceCollector | None,
    screenshot_path: str | None = None,
) -> dict[str, Any]:
    steps = step_trace.to_list() if step_trace else []
    failing_step = _infer_failing_step(steps)
    architecture_ref = None
    if failing_step:
        architecture_ref = (
            f"{failing_step.get('page_class')}.{failing_step.get('locator_id') or failing_step.get('method')}"
        )

    return {
        "schema_version": 1,
        "failure_id": failure_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
        "test": {
            "nodeid": test_nodeid,
            "file": test_file,
            "name": test_name,
        },
        "environment": {
            "base_url": base_url,
            "page_url": page_url,
        },
        "error": {
            "type": exception_type,
            "message": exception_message,
            "traceback": traceback_text,
            "playwright_hint": _parse_playwright_hint(traceback_text + exception_message),
        },
        "test_steps": steps,
        "failing_step": failing_step,
        "architecture_ref": architecture_ref,
        "artifacts": {
            "screenshot": screenshot_path,
        },
    }


def write_failure_markdown(payload: dict[str, Any]) -> str:
    test = payload["test"]
    err = payload["error"]
    steps = payload.get("test_steps") or []
    failing = payload.get("failing_step") or {}
    lines = [
        f"# Failure Report: {payload['failure_id']}",
        "",
        f"**When:** {payload['created_at']}",
        f"**Test:** `{test['nodeid']}`",
        f"**File:** `{test['file']}`",
        "",
        "## What happened",
        "",
        f"- **Error:** `{err['type']}`: {err['message'][:500]}",
        f"**URL:** {payload.get('environment', {}).get('page_url') or payload.get('environment', {}).get('base_url')}",
        "",
    ]
    if payload.get("architecture_ref"):
        lines.extend([f"**Architecture ref:** `{payload['architecture_ref']}`", ""])
    if failing:
        lines.extend(
            [
                "## Failing step",
                "",
                f"- Page: `{failing.get('page_class')}`",
                f"- Method: `{failing.get('method')}`",
                f"- Action: `{failing.get('action')}`",
                f"- Locator: `{failing.get('locator_id')}` — {failing.get('locator_summary')}",
                "",
            ]
        )
    if steps:
        lines.append("## Steps before failure")
        lines.append("")
        for step in steps:
            lines.append(
                f"{step['index'] + 1}. `{step['page_class']}.{step['method']}` "
                f"({step['action']}) — {step.get('locator_summary', '')}"
            )
        lines.append("")
    hint = err.get("playwright_hint")
    if hint:
        lines.extend(["## Playwright hint", "", f"```\n{json.dumps(hint, indent=2)}\n```", ""])
    lines.append("## Status")
    lines.append("")
    lines.append("- `processed`: false — awaiting `/healing-propose` or `python -m healing.pom_propose`")
    return "\n".join(lines)


def save_failure_report(
    payload: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> tuple[Path, Path]:
    ensure_queue_dirs()
    failure_id = payload["failure_id"]
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(write_failure_markdown(payload), encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)
    return json_path, md_path


def capture_from_exception(
    *,
    test_nodeid: str,
    test_file: str,
    test_name: str,
    base_url: str,
    page_url: str | None,
    exc: BaseException,
    step_trace: StepTraceCollector | None,
    screenshot_path: str | None = None,
) -> tuple[str, Path, Path]:
    failure_id = new_failure_id()
    payload = build_failure_payload(
        failure_id=failure_id,
        test_nodeid=test_nodeid,
        test_file=test_file,
        test_name=test_name,
        base_url=base_url,
        page_url=page_url,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback_text="".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
        step_trace=step_trace,
        screenshot_path=screenshot_path,
    )
    paths = save_failure_report(payload)
    return failure_id, paths[0], paths[1]
