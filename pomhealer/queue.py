"""Healing queue index and status machine for failures and patches."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pomhealer.paths import (
    FAILURES_DIR,
    QUEUE_APPLIED,
    QUEUE_INDEX,
    QUEUE_PATCHES,
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

TERMINAL_STATUSES = frozenset({"applied", "skipped", "deferred"})
ARCHIVE_STATUSES = frozenset({"applied", "skipped"})
PATCH_FILE_SUFFIXES = (".json", ".md", "-agent-task.md")

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


def is_patch_complete(
    proposal: dict[str, Any],
    *,
    workspace: Path | None = None,
    check_source: bool = False,
) -> bool:
    """True when architecture_updates are complete (no TODO; optional live before check)."""
    from pomhealer.patch_validate import is_proposal_complete

    return is_proposal_complete(
        proposal, workspace=workspace, check_source=check_source
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_lock_path() -> Path:
    ensure_queue_dirs()
    return QUEUE_INDEX.resolve_path().with_name("index.json.lock")


@contextmanager
def _queue_lock() -> Iterator[None]:
    """Exclusive lock around index mutations (fcntl on Unix; no-op elsewhere)."""
    ensure_queue_dirs()
    lock_path = _index_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_index_unlocked() -> dict[str, Any]:
    ensure_queue_dirs()
    if not QUEUE_INDEX.exists():
        return {"version": 1, "entries": []}
    data = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    data.setdefault("entries", [])
    return data


def _save_index_unlocked(data: dict[str, Any]) -> None:
    """Atomic write: temp file in same dir then os.replace."""
    ensure_queue_dirs()
    target = QUEUE_INDEX.resolve_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".index-", suffix=".json.tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _load_index() -> dict[str, Any]:
    with _queue_lock():
        return _load_index_unlocked()


def _save_index(data: dict[str, Any]) -> None:
    with _queue_lock():
        _save_index_unlocked(data)


def _mutate_index(mutator):
    """Load index under lock, run mutator(index), save, return mutator result."""
    with _queue_lock():
        index = _load_index_unlocked()
        result = mutator(index)
        _save_index_unlocked(index)
        return result


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

    def _mutate(index: dict[str, Any]) -> None:
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

    _mutate_index(_mutate)


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


def sort_entries_newest_first(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort queue entries by created_at descending (latest first)."""
    return sorted(entries, key=lambda e: str(e.get("created_at") or ""), reverse=True)


def list_patch_ready() -> list[dict[str, Any]]:
    index = _load_index()
    ready = [e for e in index.get("entries", []) if e.get("status") == "patch_ready"]
    return sort_entries_newest_first(ready)


def list_awaiting_agent() -> list[dict[str, Any]]:
    index = _load_index()
    awaiting = [e for e in index.get("entries", []) if e.get("status") == "awaiting_agent"]
    return sort_entries_newest_first(awaiting)


def list_deferred() -> list[dict[str, Any]]:
    index = _load_index()
    deferred = [e for e in index.get("entries", []) if e.get("status") == "deferred"]
    return sort_entries_newest_first(deferred)


def select_latest_awaiting_patches(
    entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Return awaiting_agent patches newest-first, keeping only the latest per architecture_ref.

    Entries without an architecture_ref are kept individually (keyed by patch_id).
    """
    awaiting = sort_entries_newest_first(list(entries) if entries is not None else list_awaiting_agent())
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for entry in awaiting:
        patch_id = entry.get("patch_id")
        if not patch_id:
            continue
        key = patch_id
        failure_id = entry.get("failure_id")
        if failure_id:
            try:
                failure = load_failure_payload(str(failure_id))
                ref = failure.get("architecture_ref")
                if ref:
                    key = str(ref)
            except FileNotFoundError:
                pass
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append(entry)
    return selected


def mark_failure_not_healable(failure_id: str, *, reason: str) -> None:
    def _mutate(index: dict[str, Any]) -> None:
        entry = _find_entry(index, failure_id=failure_id)
        if entry is None:
            raise KeyError(f"Unknown failure_id: {failure_id}")
        entry["status"] = "not_healable"
        entry["notes"] = reason
        entry["processed_at"] = _utc_now()

    _mutate_index(_mutate)
    payload = load_failure_payload(failure_id)
    payload["processed"] = True
    payload["classification"] = payload.get("classification") or "unknown"
    payload["not_healable_reason"] = reason
    (FAILURES_DIR / f"{failure_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )


def mark_failure_proposed(failure_id: str, patch_id: str, *, patch_json: Path, patch_md: Path) -> None:
    def _mutate(index: dict[str, Any]) -> None:
        entry = _find_entry(index, failure_id=failure_id)
        if entry is None:
            raise KeyError(f"Unknown failure_id: {failure_id}")
        entry["patch_id"] = patch_id
        entry["status"] = "awaiting_agent"
        entry["patch_json"] = str(patch_json.resolve())
        entry["patch_md"] = str(patch_md.resolve())
        entry["processed_at"] = _utc_now()

    _mutate_index(_mutate)
    payload = load_failure_payload(failure_id)
    payload["processed"] = True
    (FAILURES_DIR / f"{failure_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )


def mark_patch_ready(patch_id: str) -> None:
    """Promote an awaiting_agent patch to patch_ready after MCP completion."""
    from pomhealer.paths import get_workspace

    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    if not patch_path.exists():
        raise FileNotFoundError(f"Patch not found: {patch_path}")
    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if not is_patch_complete(proposal, workspace=get_workspace(), check_source=True):
        raise ValueError(
            f"Patch {patch_id} is incomplete (TODO placeholders, missing fields, "
            "or before no longer matches live source)."
        )
    proposal["proposal_status"] = "complete"
    patch_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    update_patch_status(patch_id, "patch_ready")


def update_patch_status(patch_id: str, status: str, *, notes: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")

    def _mutate(index: dict[str, Any]) -> None:
        entry = _find_entry(index, patch_id=patch_id)
        if entry is None:
            raise KeyError(f"Unknown patch_id: {patch_id}")
        entry["status"] = status
        entry["processed_at"] = _utc_now()
        if notes:
            entry["notes"] = notes

    _mutate_index(_mutate)


def move_patch_file(patch_id: str, dest_dir: Path) -> None:
    """Move all files for a patch out of pending patches/. Keep existing dest files."""
    dest_dir = Path(str(dest_dir))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_json: Path | None = None
    dest_md: Path | None = None
    for suffix in PATCH_FILE_SUFFIXES:
        src = Path(str(QUEUE_PATCHES / f"{patch_id}{suffix}"))
        if not src.exists():
            continue
        dest = dest_dir / src.name
        if dest.exists():
            src.unlink()
        else:
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            src.unlink()
        if suffix == ".json":
            dest_json = dest
        elif suffix == ".md":
            dest_md = dest

    if dest_json is None and dest_md is None:
        return

    def _mutate(index: dict[str, Any]) -> None:
        entry = _find_entry(index, patch_id=patch_id)
        if entry is None:
            return
        if dest_json is not None:
            entry["patch_json"] = str(dest_json.resolve())
        if dest_md is not None:
            entry["patch_md"] = str(dest_md.resolve())

    _mutate_index(_mutate)


def archive_terminal_patch_files() -> int:
    """Remove applied/skipped patch files from pending patches/ (including re-imports)."""
    moved = 0
    index = _load_index()
    for entry in index.get("entries", []):
        status = entry.get("status")
        patch_id = entry.get("patch_id")
        if not patch_id or status not in ARCHIVE_STATUSES:
            continue
        dest = QUEUE_APPLIED if status == "applied" else QUEUE_SKIPPED
        if any(Path(str(QUEUE_PATCHES / f"{patch_id}{suffix}")).exists() for suffix in PATCH_FILE_SUFFIXES):
            move_patch_file(str(patch_id), dest)
            moved += 1
    return moved


def _entry_key(entry: dict[str, Any]) -> str:
    return str(entry.get("patch_id") or entry.get("failure_id") or "")


def _entry_timestamp(entry: dict[str, Any]) -> str:
    return str(entry.get("processed_at") or entry.get("created_at") or "")


def choose_merged_entry(local: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Prefer local terminal statuses over incoming patch_ready; otherwise newer stamp."""
    local_status = str(local.get("status") or "")
    incoming_status = str(incoming.get("status") or "")
    if local_status in TERMINAL_STATUSES and incoming_status == "patch_ready":
        return local
    if incoming_status in TERMINAL_STATUSES and local_status not in TERMINAL_STATUSES:
        return incoming
    if _entry_timestamp(incoming) > _entry_timestamp(local):
        return incoming
    return local


def merge_index_entries(incoming_entries: list[dict[str, Any]]) -> int:
    """Merge imported queue entries into the local index. Returns upsert count."""

    def _mutate(index: dict[str, Any]) -> int:
        by_key: dict[str, dict[str, Any]] = {}
        order: list[tuple[str, Any]] = []
        for entry in index.get("entries", []):
            key = _entry_key(entry)
            if not key:
                order.append(("raw", entry))
                continue
            by_key[key] = entry
            order.append(("key", key))
        upserts = 0
        for incoming in incoming_entries:
            key = _entry_key(incoming)
            if not key:
                continue
            if key in by_key:
                chosen = choose_merged_entry(by_key[key], incoming)
                if chosen is incoming:
                    by_key[key] = incoming
                    upserts += 1
            else:
                by_key[key] = incoming
                order.append(("key", key))
                upserts += 1
        new_entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for kind, value in order:
            if kind == "raw":
                new_entries.append(value)
            elif value not in seen:
                new_entries.append(by_key[value])
                seen.add(value)
        index["entries"] = new_entries
        return upserts

    return int(_mutate_index(_mutate))


def get_index_summary() -> dict[str, int]:
    index = _load_index()
    counts = {s: 0 for s in STATUSES}
    for entry in index.get("entries", []):
        status = entry.get("status", "pending_proposal")
        counts[status] = counts.get(status, 0) + 1
    return counts
