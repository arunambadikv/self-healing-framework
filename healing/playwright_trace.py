"""Auto-instrument Playwright Locator/Page actions for healing step traces.

Installed by the pytest plugin so consumer POMs do not need BasePage helpers
for ``test_steps`` recording. Stack frames under ``pages/`` attribute each step;
``BasePage`` helpers can suppress auto-trace after they call ``record_step``
themselves to avoid duplicates while keeping explicit ``locator_id`` values.
"""

from __future__ import annotations

import contextvars
import inspect
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from healing.step_trace import record_step

_suppress_auto_trace: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "healing_suppress_auto_trace", default=False
)
_in_auto_trace: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "healing_in_auto_trace", default=False
)

_installed = False
_originals: dict[tuple[type, str], Callable[..., Any]] = {}

_BASE_PAGE_HELPERS = frozenset(
    {
        "_click_locator",
        "_fill_locator",
        "_check_locator",
        "_uncheck_locator",
        "_select_locator",
        "_expect_visible",
        "_drag_to",
        "_record",
        "goto",
    }
)

_LOCATOR_ACTIONS: dict[str, str] = {
    "click": "click",
    "dblclick": "dblclick",
    "fill": "fill",
    "check": "check",
    "uncheck": "uncheck",
    "select_option": "select_option",
    "drag_to": "drag_to",
    "hover": "hover",
    "press": "press",
    "clear": "clear",
    "type": "type",
    "tap": "tap",
}

_PAGE_ACTIONS: dict[str, str] = {
    "goto": "navigate",
}

_EXPECT_ACTIONS: dict[str, str] = {
    "to_be_visible": "expect_visible",
    "to_be_hidden": "expect_hidden",
    "to_be_enabled": "expect_enabled",
    "to_be_disabled": "expect_disabled",
    "to_have_text": "expect_text",
    "to_have_value": "expect_value",
    "to_be_checked": "expect_checked",
    "to_be_editable": "expect_editable",
    "to_be_empty": "expect_empty",
    "to_be_focused": "expect_focused",
    "to_contain_text": "expect_contain_text",
}


@dataclass(frozen=True)
class StackFrameInfo:
    filename: str
    function: str
    locals: dict[str, Any]


@dataclass(frozen=True)
class StepAttribution:
    page_class: str
    method: str
    locator_id: str | None


def module_stem_to_page_class(stem: str) -> str:
    return "".join(part.capitalize() for part in stem.split("_") if part)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_healing_internal(filename: str) -> bool:
    norm = _norm_path(filename)
    return bool(
        re.search(r"/healing/(playwright_trace|step_trace|pytest_plugin)\.py$", norm)
    )


def _is_base_page_file(filename: str) -> bool:
    norm = _norm_path(filename)
    return norm.endswith("/healing/base_page.py") or norm.endswith("/pages/base_page.py")


def _pages_module_stem(filename: str) -> str | None:
    norm = _norm_path(filename)
    match = re.search(r"/pages/([A-Za-z_][\w]*)\.py$", norm)
    if not match:
        return None
    stem = match.group(1)
    if stem == "base_page" or stem == "__init__":
        return None
    return stem


def attribute_from_frames(frames: list[StackFrameInfo]) -> StepAttribution:
    """Map a call stack to page_class / method / locator_id."""
    locator_id: str | None = None
    for frame in frames:
        if _is_healing_internal(frame.filename):
            continue
        if _is_base_page_file(frame.filename):
            if frame.function in _BASE_PAGE_HELPERS:
                helper_id = frame.locals.get("locator_id")
                if isinstance(helper_id, str) and helper_id:
                    locator_id = helper_id
                elif frame.function == "_drag_to":
                    source_id = frame.locals.get("source_id")
                    if isinstance(source_id, str) and source_id:
                        locator_id = source_id
            continue

        stem = _pages_module_stem(frame.filename)
        if stem is None:
            continue

        method = frame.function
        if method in {"<module>", "<lambda>"}:
            continue

        self_obj = frame.locals.get("self")
        if self_obj is not None:
            page_class = type(self_obj).__name__
        else:
            page_class = module_stem_to_page_class(stem)

        if locator_id is None:
            locator_id = method
        return StepAttribution(page_class=page_class, method=method, locator_id=locator_id)

    return StepAttribution(page_class="UnknownPage", method="unknown", locator_id=None)


def attribute_from_stack(depth: int = 1) -> StepAttribution:
    frames: list[StackFrameInfo] = []
    for info in inspect.stack()[depth:]:
        try:
            local_vars = dict(info.frame.f_locals)
        except Exception:
            local_vars = {}
        frames.append(
            StackFrameInfo(
                filename=info.filename,
                function=info.function,
                locals=local_vars,
            )
        )
    return attribute_from_frames(frames)


def locator_summary(target: Any, *, action: str, extra: str = "") -> str:
    text = ""
    try:
        text = str(target)
    except Exception:
        text = type(target).__name__
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 160:
        text = text[:157] + "..."
    if extra:
        return f"{action}:{text} ({extra})" if text else f"{action} ({extra})"
    return f"{action}:{text}" if text else action


@contextmanager
def suppress_auto_trace() -> Iterator[None]:
    """Disable Playwright auto-trace while BasePage records an explicit step."""
    token = _suppress_auto_trace.set(True)
    try:
        yield
    finally:
        _suppress_auto_trace.reset(token)


def _should_auto_record() -> bool:
    if _suppress_auto_trace.get():
        return False
    if _in_auto_trace.get():
        return False
    from healing.step_trace import get_active_step_trace

    return get_active_step_trace() is not None


def _auto_record(action: str, target: Any = None, *, extra: str = "") -> None:
    if not _should_auto_record():
        return
    token = _in_auto_trace.set(True)
    try:
        attr = attribute_from_stack(depth=1)
        record_step(
            page_class=attr.page_class,
            method=attr.method,
            action=action,
            locator_id=attr.locator_id,
            locator_summary=locator_summary(target, action=action, extra=extra)
            if target is not None
            else (extra or action),
        )
    finally:
        _in_auto_trace.reset(token)


def _wrap_method(
    cls: type,
    method_name: str,
    action: str,
    *,
    target_from_self: bool = True,
) -> None:
    key = (cls, method_name)
    if key in _originals:
        return
    original = getattr(cls, method_name, None)
    if original is None or not callable(original):
        return
    _originals[key] = original

    def wrapped(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        extra = ""
        if action == "fill" and args:
            extra = f"value={args[0]!r}"
        elif action == "navigate" and args:
            extra = f"url={args[0]!r}"
        elif action == "select_option" and args:
            extra = f"value={args[0]!r}"
        _auto_record(action, self if target_from_self else None, extra=extra)
        return _originals[key](self, *args, **kwargs)

    setattr(cls, method_name, wrapped)


def install_playwright_tracing() -> bool:
    """Patch Playwright sync Locator/Page (and expect assertions when available).

    Returns True when patches were applied (or already installed).
    """
    global _installed
    if _installed:
        return True
    try:
        from playwright.sync_api import Locator, Page
    except ImportError:
        return False

    for method_name, action in _LOCATOR_ACTIONS.items():
        _wrap_method(Locator, method_name, action)

    for method_name, action in _PAGE_ACTIONS.items():
        _wrap_method(Page, method_name, action)

    assertion_cls = None
    for import_path in (
        ("playwright.sync_api", "LocatorAssertions"),
        ("playwright._impl._assertions", "LocatorAssertions"),
    ):
        try:
            module = __import__(import_path[0], fromlist=[import_path[1]])
            assertion_cls = getattr(module, import_path[1], None)
            if assertion_cls is not None:
                break
        except ImportError:
            continue

    if assertion_cls is not None:
        for method_name, action in _EXPECT_ACTIONS.items():
            _wrap_method(assertion_cls, method_name, action)

    _installed = True
    return True


def uninstall_playwright_tracing() -> None:
    """Restore original Playwright methods (for tests / session teardown)."""
    global _installed
    for (cls, method_name), original in list(_originals.items()):
        setattr(cls, method_name, original)
        del _originals[(cls, method_name)]
    _installed = False


def is_playwright_tracing_installed() -> bool:
    return _installed
