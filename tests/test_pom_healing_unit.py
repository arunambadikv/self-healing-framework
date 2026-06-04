"""Unit tests for POM healing queue and architecture scan."""

import json
from pathlib import Path

from healing.architecture_scan import build_manifest
from healing.healing_queue import register_failure, list_unprocessed_failures, mark_failure_proposed
from healing.paths import ensure_queue_dirs, FAILURES_DIR, QUEUE_INDEX


def test_build_manifest_includes_demo_page(tmp_path: Path, monkeypatch):
    workspace = Path(__file__).resolve().parents[1]
    manifest = build_manifest(workspace)
    assert "DemoPage" in manifest.get("pages", {})
    assert manifest.get("content_hash")


def test_healing_queue_register_and_propose(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_queue_dirs()
    failure_id = "F-test123456"
    payload = {
        "failure_id": failure_id,
        "processed": False,
        "test": {"nodeid": "t", "file": "tests/t.py", "name": "t"},
        "error": {"type": "E", "message": "fail"},
    }
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    md_path.write_text("# fail", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)
    assert list_unprocessed_failures()
    patch_id = "P-test123456"
    patch_json = tmp_path / "artifacts/healing-queue/patches" / f"{patch_id}.json"
    patch_json.parent.mkdir(parents=True, exist_ok=True)
    patch_json.write_text('{"proposal": {"patch_id": "P-test"}}', encoding="utf-8")
    patch_md = patch_json.with_suffix(".md")
    patch_md.write_text("# patch", encoding="utf-8")
    mark_failure_proposed(failure_id, patch_id, patch_json=patch_json, patch_md=patch_md)
    assert not list_unprocessed_failures()
    index = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    assert index["entries"][0]["status"] == "patch_ready"
