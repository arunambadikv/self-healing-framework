"""Per-pytest-session counters for healing automation."""

from __future__ import annotations

_healable_failure_count = 0


def reset_session_state() -> None:
    global _healable_failure_count
    _healable_failure_count = 0


def note_healable_failure() -> None:
    global _healable_failure_count
    _healable_failure_count += 1


def session_had_healable_failures() -> bool:
    return _healable_failure_count > 0
