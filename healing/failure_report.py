"""Capture and persist detailed pytest failure reports (F-*.json / F-*.md)."""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healing.artifact_naming import build_artifact_id
from healing.paths import FAILURES_DIR, ensure_queue_dirs
from healing.healing_queue import register_failure
from healing.failure_classifier import classify_failure, is_healable
from healing.step_trace import StepTraceCollector


def new_failure_id(test_name: str | None = None) -> str:
    """Readable id: F-{test-name}-{YYYYMMDD-HHMMSS} (with -2/-3 on collision)."""
    ensure_queue_dirs()
    return build_artifact_id(
        "F",
        test_name,
        directory=Path(str(FAILURES_DIR)),
        suffixes=(".json", ".md"),
    )


def _parse_playwright_hint(exc_repr: str) -> dict[str, Any] | None:
    hint: dict[str, Any] = {}
    if "Locator" in exc_repr or "get_by_" in exc_repr or "locator(" in exc_repr:
        hint["kind"] = "locator"
    for pattern in (
        r"get_by_role\([^)]+\)",
        r"get_by_text\([^)]+\)",
        r"locator\([^)]+\)",
        r"get_by_placeholder\([^)]+\)",
        r'waiting for locator\("([^"]+)"\)',
        r"waiting for locator\('([^']+)'\)",
    ):
        match = re.search(pattern, exc_repr)
        if match:
            hint["expression"] = match.group(0)
            if match.lastindex:
                hint["selector"] = match.group(1)
            break
    return hint or None


def _module_stem_to_page_class(stem: str) -> str:
    return "".join(part.capitalize() for part in stem.split("_") if part)


def infer_architecture_from_traceback(traceback_text: str) -> dict[str, Any] | None:
    """Infer page method from pytest/Playwright traceback when step tracing is absent.

    Prefer package auto-instrumentation (``healing.playwright_trace``) or BasePage
    helpers. This fallback still marks failures healable when the traceback points
    at ``pages/*.py`` (blocking HEALING_MCP_AUTO otherwise).
    """
    patterns = (
        # pytest short TB: pages/login_page.py:18: in click_submit_wrong
        r"pages[/\\]([A-Za-z_][\w]*)\.py:\d+:\s+in\s+([A-Za-z_][\w]*)",
        # full TB: File ".../pages/practice_page.py", line 19, in open_test_table_wrong
        r'File "[^"]*pages[/\\]([A-Za-z_][\w]*)\.py", line \d+, in ([A-Za-z_][\w]*)',
    )
    match = None
    for pattern in patterns:
        match = re.search(pattern, traceback_text)
        if match:
            break
    if not match:
        return None
    stem, method = match.group(1), match.group(2)
    if method in {"goto", "navigate", "<module>"}:
        return None
    page_class = _module_stem_to_page_class(stem)
    return {
        "page_class": page_class,
        "method": method,
        "locator_id": method,
        "action": "interact",
        "architecture_ref": f"{page_class}.{method}",
    }


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
    storage_state_path: str | None = None,
) -> dict[str, Any]:
    steps = step_trace.to_list() if step_trace else []
    failing_step = _infer_failing_step(steps)
    architecture_ref = None
    if failing_step:
        architecture_ref = (
            f"{failing_step.get('page_class')}.{failing_step.get('locator_id') or failing_step.get('method')}"
        )

    # Consumer pages that click locators without BasePage step tracing still need a ref.
    if not architecture_ref:
        inferred = infer_architecture_from_traceback(traceback_text)
        if inferred:
            architecture_ref = inferred["architecture_ref"]
            failing_step = {
                "index": 0,
                "page_class": inferred["page_class"],
                "method": inferred["method"],
                "action": inferred["action"],
                "locator_id": inferred["locator_id"],
                "locator_summary": inferred["architecture_ref"],
                "inferred": True,
            }
            if not steps:
                steps = [failing_step]

    artifacts: dict[str, Any] = {
        "screenshot": screenshot_path,
    }
    if storage_state_path:
        artifacts["storage_state"] = storage_state_path

    payload = {
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
        "artifacts": artifacts,
    }
    payload["classification"] = classify_failure(payload)
    payload["healable"] = is_healable(payload)
    return payload


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
    if payload.get("classification"):
        lines.extend([f"**Classification:** `{payload['classification']}`", ""])
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
    artifacts = payload.get("artifacts") or {}
    if artifacts.get("screenshot"):
        lines.extend(
            [
                "## Screenshot",
                "",
                f"- **screenshot:** `{artifacts['screenshot']}`",
                "- Open this PNG when reviewing; agents should Read the image before deciding heal/skip/defer.",
                "",
            ]
        )
    if artifacts.get("storage_state"):
        lines.extend(
            [
                "## Session restore",
                "",
                f"- **storage_state:** `{artifacts['storage_state']}`",
                "- MCP propose should load this state, then navigate to `page_url` before snapshot.",
                "",
            ]
        )
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
    initial_status = "not_healable" if not payload.get("healable") else "pending_proposal"
    register_failure(failure_id, json_path=json_path, md_path=md_path, status=initial_status)
    if payload.get("healable"):
        from healing.session_state import note_healable_failure

        note_healable_failure(failure_id)
    from healing.healing_reports import emit_failure_captured

    emit_failure_captured(payload)
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
    storage_state_path: str | None = None,
    failure_id: str | None = None,
) -> tuple[str, Path, Path]:
    failure_id = failure_id or new_failure_id(test_name)
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
        storage_state_path=storage_state_path,
    )
    paths = save_failure_report(payload)
    return failure_id, paths[0], paths[1]
