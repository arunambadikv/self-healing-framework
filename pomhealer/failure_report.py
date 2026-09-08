"""Capture and persist detailed pytest failure reports (F-*.json / F-*.md)."""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pomhealer.artifact_naming import build_artifact_id
from pomhealer.paths import FAILURES_DIR, ensure_queue_dirs
from pomhealer.queue import register_failure
from pomhealer.failure_classifier import classify_failure, is_healable
from pomhealer.step_trace import StepTraceCollector


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

    Prefer package auto-instrumentation (``pomhealer.playwright_trace``) or BasePage
    helpers. This fallback still marks failures healable when the traceback points
    at ``pages/*.py`` (blocking POMHEALER_MCP_AUTO otherwise).

    When the failing frame is a page method that wraps a raw locator, prefer an
    existing ``@property`` whose expression matches the Playwright wait hint.
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
    locator_id = method
    architecture_ref = f"{page_class}.{method}"

    property_name = _match_property_from_traceback(stem, traceback_text)
    if property_name:
        locator_id = property_name
        architecture_ref = f"{page_class}.{property_name}"

    return {
        "page_class": page_class,
        "method": method,
        "locator_id": locator_id,
        "action": "interact",
        "architecture_ref": architecture_ref,
    }


def _extract_playwright_selector_hints(traceback_text: str) -> list[str]:
    hints: list[str] = []
    for pattern in (
        r'waiting for locator\("([^"]+)"\)',
        r"waiting for locator\('([^']+)'\)",
        r'locator\("([^"]+)"\)',
        r"locator\('([^']+)'\)",
        r'get_by_role\([^)]+\)',
        r'get_by_text\([^)]+\)',
        r'get_by_placeholder\([^)]+\)',
    ):
        for match in re.finditer(pattern, traceback_text):
            hints.append(match.group(0) if match.lastindex is None else match.group(1))
    return hints


def _match_property_from_traceback(module_stem: str, traceback_text: str) -> str | None:
    """If a page @property expression matches a Playwright hint, return that property name."""
    from pomhealer.paths import get_workspace

    workspace = get_workspace()
    page_path = workspace / "pages" / f"{module_stem}.py"
    if not page_path.is_file():
        return None
    try:
        source = page_path.read_text(encoding="utf-8")
    except OSError:
        return None

    hints = _extract_playwright_selector_hints(traceback_text)
    if not hints:
        return None

    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if not any(
                isinstance(d, ast.Name) and d.id == "property" for d in item.decorator_list
            ):
                continue
            from pomhealer.locator_source import extract_property_return_expression

            expr = extract_property_return_expression(source, item.name) or ""
            for hint in hints:
                if hint and hint in expr:
                    return item.name
                # Constant attrs referenced by methods (e.g. self.WRONG_TABLE_LINK = "#x")
                if hint and hint in source and f"{item.name}" in expr:
                    # Prefer property only when expression embeds the hint
                    pass
            # Match class-level string constants used in methods that equal the hint
            for hint in hints:
                const_pat = rf'{re.escape(item.name)}\s*=\s*["\']({re.escape(hint)})["\']'
                if re.search(const_pat, source):
                    return item.name
    # Also match module/class attributes that equal the selector (used by raw locator methods)
    for hint in hints:
        if not hint:
            continue
        attr_match = re.search(
            rf'([A-Z_][A-Z0-9_]*)\s*=\s*["\']{re.escape(hint)}["\']',
            source,
        )
        if attr_match:
            # Prefer a property that returns that constant if present
            attr = attr_match.group(1)
            prop_match = re.search(
                rf"@property\s+def\s+(\w+)\s*\([^)]*\):[^\n]*\n(?:\s+\"\"\"[^\"]*\"\"\"\s*\n)?\s+return\s+self\.{attr}",
                source,
            )
            if prop_match:
                return prop_match.group(1)
    return None


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
    lines.append("- `processed`: false — awaiting `/pomhealer-propose` or `python -m pomhealer.pom_propose`")
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
        from pomhealer.session_state import note_healable_failure

        note_healable_failure(failure_id)
    from pomhealer.reports import emit_failure_captured

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
