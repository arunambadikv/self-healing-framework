"""Healing queue index and status machine for failures and patches."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healing.paths import (
    FAILURES_DIR,
    QUEUE_APPLIED,
    QUEUE_INDEX,
    QUEUE_PATCHES,
    QUEUE_PENDING,
    QUEUE_SKIPPED,
    ensure_queue_dirs,
)

STATUSES = frozenset(
    {
        "pending_proposal",
        "awaiting_agent",
        "patch_ready",
        "applied",
        "skipped",
        "deferred",
        "not_healable",
    }
)


def is_patch_complete(proposal: dict[str, Any]) -> bool:
    """True when architecture_updates have MCP-verified locator expressions (no TODO)."""
    updates = proposal.get("architecture_updates") or []
    if not updates:
        return False
    return not any("TODO" in str(u.get("after", "")) for u in updates)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_index() -> dict[str, Any]:
    ensure_queue_dirs()
    if not QUEUE_INDEX.exists():
        return {"version": 1, "entries": []}
    data = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    data.setdefault("entries", [])
    return data


def _save_index(data: dict[str, Any]) -> None:
    ensure_queue_dirs()
    QUEUE_INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _find_entry(index: dict[str, Any], *, failure_id: str | None = None, patch_id: str | None = None) -> dict[str, Any] | None:
    for entry in index.get("entries", []):
        if failure_id and entry.get("failure_id") == failure_id:
            return entry
        if patch_id and entry.get("patch_id") == patch_id:
            return entry
    return None


def register_failure(
    failure_id: str,
    *,
    json_path: Path,
    md_path: Path,
    status: str = "pending_proposal",
) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    index = _load_index()
    if _find_entry(index, failure_id=failure_id):
        return
    index["entries"].append(
        {
            "failure_id": failure_id,
            "patch_id": None,
            "status": status,
            "failure_json": str(json_path.resolve()),
            "failure_md": str(md_path.resolve()),
            "patch_json": None,
            "patch_md": None,
            "created_at": _utc_now(),
            "processed_at": None,
        }
    )
    pending_link = QUEUE_PENDING / f"{failure_id}.json"
    pending_link.write_text(
        json.dumps({"failure_id": failure_id, "failure_json": str(json_path.resolve())}, indent=2),
        encoding="utf-8",
    )
    _save_index(index)


def load_failure_payload(failure_id: str) -> dict[str, Any]:
    path = FAILURES_DIR / f"{failure_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Failure report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_unprocessed_failures() -> list[dict[str, Any]]:
    index = _load_index()
    result: list[dict[str, Any]] = []
    for entry in index.get("entries", []):
        if entry.get("status") == "pending_proposal":
            result.append(entry)
    return result


def list_patch_ready() -> list[dict[str, Any]]:
    index = _load_index()
    return [e for e in index.get("entries", []) if e.get("status") == "patch_ready"]


def list_awaiting_agent() -> list[dict[str, Any]]:
    index = _load_index()
    return [e for e in index.get("entries", []) if e.get("status") == "awaiting_agent"]


def mark_failure_not_healable(failure_id: str, *, reason: str) -> None:
    index = _load_index()
    entry = _find_entry(index, failure_id=failure_id)
    if entry is None:
        raise KeyError(f"Unknown failure_id: {failure_id}")
    entry["status"] = "not_healable"
    entry["notes"] = reason
    entry["processed_at"] = _utc_now()
    pending = QUEUE_PENDING / f"{failure_id}.json"
    if pending.exists():
        pending.unlink()
    payload = load_failure_payload(failure_id)
    payload["processed"] = True
    payload["classification"] = payload.get("classification") or "unknown"
    payload["not_healable_reason"] = reason
    (FAILURES_DIR / f"{failure_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    _save_index(index)


def mark_failure_proposed(failure_id: str, patch_id: str, *, patch_json: Path, patch_md: Path) -> None:
    index = _load_index()
    entry = _find_entry(index, failure_id=failure_id)
    if entry is None:
        raise KeyError(f"Unknown failure_id: {failure_id}")
    entry["patch_id"] = patch_id
    entry["status"] = "awaiting_agent"
    entry["patch_json"] = str(patch_json.resolve())
    entry["patch_md"] = str(patch_md.resolve())
    entry["processed_at"] = _utc_now()
    pending = QUEUE_PENDING / f"{failure_id}.json"
    if pending.exists():
        pending.unlink()
    payload = load_failure_payload(failure_id)
    payload["processed"] = True
    (FAILURES_DIR / f"{failure_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    _save_index(index)


def mark_patch_ready(patch_id: str) -> None:
    """Promote an awaiting_agent patch to patch_ready after MCP completion."""
    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    if not patch_path.exists():
        raise FileNotFoundError(f"Patch not found: {patch_path}")
    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if not is_patch_complete(proposal):
        raise ValueError(
            f"Patch {patch_id} is incomplete (TODO placeholders or awaiting_agent status)."
        )
    proposal["proposal_status"] = "complete"
    patch_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    update_patch_status(patch_id, "patch_ready")


def update_patch_status(patch_id: str, status: str, *, notes: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    index = _load_index()
    entry = _find_entry(index, patch_id=patch_id)
    if entry is None:
        raise KeyError(f"Unknown patch_id: {patch_id}")
    entry["status"] = status
    entry["processed_at"] = _utc_now()
    if notes:
        entry["notes"] = notes
    _save_index(index)


def move_patch_file(patch_id: str, dest_dir: Path) -> None:
    for ext in (".json", ".md"):
        src = QUEUE_PATCHES / f"{patch_id}{ext}"
        if src.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            src.unlink()


def get_index_summary() -> dict[str, int]:
    index = _load_index()
    counts = {s: 0 for s in STATUSES}
    for entry in index.get("entries", []):
        status = entry.get("status", "pending_proposal")
        counts[status] = counts.get(status, 0) + 1
    return counts
