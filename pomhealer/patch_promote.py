"""Promote completed patch proposals from awaiting_agent to patch_ready."""

from __future__ import annotations

from pomhealer.queue import is_patch_complete, list_awaiting_agent, mark_patch_ready
from pomhealer.paths import QUEUE_PATCHES
from pomhealer.pom_apply import load_patch


def promote_patch(patch_id: str) -> None:
    """Promote a patch to patch_ready when proposal content is complete."""
    mark_patch_ready(patch_id)
    payload = load_patch(patch_id, QUEUE_PATCHES)
    proposal = payload.get("proposal") or payload
    from pomhealer.reports import emit_patch_ready

    emit_patch_ready(patch_id, proposal)


def promote_all_complete() -> list[str]:
    """Promote every awaiting_agent patch whose JSON has no TODO placeholders."""
    promoted: list[str] = []
    for entry in list_awaiting_agent():
        patch_id = entry.get("patch_id")
        if not patch_id:
            continue
        try:
            payload = load_patch(patch_id, QUEUE_PATCHES)
            proposal = payload.get("proposal") or payload
            if not is_patch_complete(proposal, check_source=True):
                continue
            promote_patch(patch_id)
            promoted.append(patch_id)
        except (FileNotFoundError, ValueError, KeyError):
            continue
    return promoted
