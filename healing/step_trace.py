"""Per-test step trace for failure reports."""

from __future__ import annotations

import contextvars
from dataclasses import asdict, dataclass, field
from typing import Any

_step_trace: contextvars.ContextVar[StepTraceCollector | None] = contextvars.ContextVar(
    "healing_step_trace", default=None
)


@dataclass
class TestStep:
    index: int
    page_class: str
    method: str
    action: str
    locator_id: str | None
    locator_summary: str


@dataclass
class StepTraceCollector:
    test_name: str
    test_module: str
    steps: list[TestStep] = field(default_factory=list)

    def append(
        self,
        *,
        page_class: str,
        method: str,
        action: str,
        locator_id: str | None = None,
        locator_summary: str = "",
    ) -> None:
        self.steps.append(
            TestStep(
                index=len(self.steps),
                page_class=page_class,
                method=method,
                action=action,
                locator_id=locator_id,
                locator_summary=locator_summary,
            )
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(s) for s in self.steps]


def set_active_step_trace(collector: StepTraceCollector | None):
    return _step_trace.set(collector)


def reset_step_trace(token) -> None:
    _step_trace.reset(token)


def get_active_step_trace() -> StepTraceCollector | None:
    return _step_trace.get()


def record_step(
    *,
    page_class: str,
    method: str,
    action: str,
    locator_id: str | None = None,
    locator_summary: str = "",
) -> None:
    collector = _step_trace.get()
    if collector is None:
        return
    collector.append(
        page_class=page_class,
        method=method,
        action=action,
        locator_id=locator_id,
        locator_summary=locator_summary or locator_id or method,
    )
