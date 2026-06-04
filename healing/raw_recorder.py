"""Record successful raw Playwright locator actions without changing test behavior."""

from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from playwright.sync_api import Locator, Page

_current_collector: contextvars.ContextVar[RawObservationCollector | None] = contextvars.ContextVar(
    "healing_raw_collector", default=None
)

_LOCATOR_ACTIONS = (
    "click",
    "dblclick",
    "fill",
    "check",
    "uncheck",
    "select_option",
    "press",
    "set_input_files",
    "tap",
)

_PATCHED = False
_ORIGINAL_ACTIONS: dict[str, Callable[..., Any]] = {}


@dataclass
class RawObservation:
    semantic_key: str
    action: str
    candidate: dict[str, Any]
    intent: str
    test_name: str


@dataclass
class RawObservationCollector:
    test_name: str
    test_module: str
    observations: list[RawObservation] = field(default_factory=list)
    _seen: set[tuple[str, str, str]] = field(default_factory=set)

    def record(self, *, candidate: dict[str, Any], action: str) -> None:
        key = make_semantic_key(self.test_module, action, candidate)
        dedupe_key = (
            key,
            action,
            candidate.get("type", ""),
            str(candidate.get("value") or candidate.get("role") or candidate.get("name")),
        )
        if dedupe_key in self._seen:
            return
        self._seen.add(dedupe_key)

        intent = describe_intent(action, candidate)
        self.observations.append(
            RawObservation(
                semantic_key=key,
                action=action,
                candidate=candidate,
                intent=intent,
                test_name=self.test_name,
            )
        )


def _slug(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "element"


def make_semantic_key(test_module: str, action: str, candidate: dict[str, Any]) -> str:
    ctype = candidate.get("type", "unknown")
    if ctype == "role":
        part = _slug(f"{candidate.get('role', 'role')}_{candidate.get('name') or 'unnamed'}")
    elif ctype in {"text", "label", "placeholder", "test_id", "css"}:
        part = _slug(str(candidate.get("value", "element")))
    else:
        part = "element"
    module = _slug(test_module.replace("test_", ""))
    return f"auto.{module}.{action}_{part}"


def describe_intent(action: str, candidate: dict[str, Any]) -> str:
    ctype = candidate.get("type")
    if ctype == "role":
        name = candidate.get("name") or ""
        return f"{action} {candidate.get('role')} '{name}'".strip()
    if ctype in {"text", "label", "placeholder", "test_id", "css"}:
        return f"{action} element ({ctype}={candidate.get('value')})"
    return f"{action} element ({ctype})"


def _attach_meta(locator: Locator, *, candidate: dict[str, Any], default_action: str) -> Locator:
    locator._healing_candidate = candidate  # type: ignore[attr-defined]
    locator._healing_default_action = default_action  # type: ignore[attr-defined]
    return locator


def _candidate_from_locator(selector: str) -> dict[str, Any]:
    return {"type": "css", "value": selector}


def _candidate_from_role(role: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    candidate: dict[str, Any] = {"type": "role", "role": role}
    if kwargs.get("name") is not None:
        candidate["name"] = kwargs["name"]
    return candidate


def _candidate_from_value(ctype: str, value: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    candidate: dict[str, Any] = {"type": ctype, "value": value}
    if kwargs.get("exact") is not None:
        candidate["exact"] = bool(kwargs["exact"])
    return candidate


def instrument_page(page: Page) -> None:
    """Tag locators created through common Page factory methods."""

    def wrap_factory(
        method_name: str,
        build_candidate: Callable[..., dict[str, Any]],
        default_action: str,
    ):
        original = getattr(page, method_name)

        def wrapper(*args, **kwargs):
            locator = original(*args, **kwargs)
            candidate = build_candidate(*args, **kwargs)
            return _attach_meta(locator, candidate=candidate, default_action=default_action)

        setattr(page, method_name, wrapper)

    wrap_factory("locator", lambda selector, **kw: _candidate_from_locator(selector), "click")
    wrap_factory("get_by_role", lambda role, **kw: _candidate_from_role(role, kw), "click")
    wrap_factory("get_by_text", lambda text, **kw: _candidate_from_value("text", text, kw), "expect_visible")
    wrap_factory("get_by_label", lambda value, **kw: _candidate_from_value("label", value, kw), "click")
    wrap_factory(
        "get_by_placeholder",
        lambda value, **kw: _candidate_from_value("placeholder", value, kw),
        "fill",
    )
    wrap_factory("get_by_test_id", lambda value, **kw: _candidate_from_value("test_id", value, kw), "click")
    wrap_factory("get_by_alt_text", lambda value, **kw: _candidate_from_value("text", value, kw), "click")
    wrap_factory("get_by_title", lambda value, **kw: _candidate_from_value("text", value, kw), "click")


def _infer_action(method_name: str, locator: Locator) -> str:
    default = getattr(locator, "_healing_default_action", "click")
    if method_name == "fill":
        return "fill"
    if method_name == "select_option":
        return "select_option"
    if method_name == "check":
        return "check"
    if method_name == "uncheck":
        return "uncheck"
    if method_name == "press":
        return "fill"
    return default


def _record_success(locator: Locator, action: str) -> None:
    collector = _current_collector.get()
    candidate = getattr(locator, "_healing_candidate", None)
    if collector is None or not isinstance(candidate, dict):
        return
    collector.record(candidate=candidate, action=action)


def _make_action_wrapper(method_name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(locator_self: Locator, *args, **kwargs):
        result = original(locator_self, *args, **kwargs)
        action = _infer_action(method_name, locator_self)
        _record_success(locator_self, action)
        return result

    return wrapper


def install_locator_action_hooks() -> None:
    global _PATCHED
    if _PATCHED:
        return
    for method_name in _LOCATOR_ACTIONS:
        original = getattr(Locator, method_name)
        _ORIGINAL_ACTIONS[method_name] = original
        setattr(Locator, method_name, _make_action_wrapper(method_name, original))

    original_wait_for = Locator.wait_for
    _ORIGINAL_ACTIONS["wait_for"] = original_wait_for

    def wait_for_wrapper(locator_self: Locator, *args, **kwargs):
        result = original_wait_for(locator_self, *args, **kwargs)
        state = kwargs.get("state")
        if args and state is None:
            state = args[0]
        if state in (None, "visible", "attached") and hasattr(locator_self, "_healing_candidate"):
            action = getattr(locator_self, "_healing_default_action", "expect_visible")
            if action == "expect_visible" or state == "visible":
                _record_success(locator_self, "expect_visible")
        return result

    Locator.wait_for = wait_for_wrapper  # type: ignore[method-assign]
    _PATCHED = True


def set_active_collector(collector: RawObservationCollector | None):
    return _current_collector.set(collector)


def reset_collector(token) -> None:
    _current_collector.reset(token)
