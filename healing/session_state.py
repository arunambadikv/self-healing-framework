"""Per-pytest-session counters for healing automation."""

from __future__ import annotations

_healable_failure_ids: set[str] = set()
_new_patch_ids: set[str] = set()


def reset_session_state() -> None:
    global _healable_failure_ids, _new_patch_ids
    _healable_failure_ids = set()
    _new_patch_ids = set()


def note_healable_failure(failure_id: str | None = None) -> None:
    """Record a healable failure captured in this pytest session."""
    if failure_id:
        _healable_failure_ids.add(failure_id)
    else:
        # Backward-compatible counter bump when id is unknown
        _healable_failure_ids.add(f"__anon_{len(_healable_failure_ids)}")


def note_session_patch(patch_id: str) -> None:
    """Record a patch created or linked for MCP in this session."""
    if patch_id:
        _new_patch_ids.add(patch_id)


def session_had_healable_failures() -> bool:
    return bool(_healable_failure_ids)


def session_healable_failure_ids() -> frozenset[str]:
    return frozenset(fid for fid in _healable_failure_ids if not fid.startswith("__anon_"))


def session_new_patch_ids() -> frozenset[str]:
    return frozenset(_new_patch_ids)
