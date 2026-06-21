"""Unit tests for POM healing queue and architecture scan."""

import json
from pathlib import Path

from healing.architecture_scan import build_manifest
from healing.healing_queue import (
    is_patch_complete,
    mark_failure_proposed,
    mark_patch_ready,
    register_failure,
    list_unprocessed_failures,
)
from healing.failure_classifier import classify_failure, is_healable
from healing.paths import ensure_queue_dirs, FAILURES_DIR, QUEUE_INDEX


def test_build_manifest_includes_demo_page(tmp_path: Path, monkeypatch):
    workspace = Path(__file__).resolve().parents[1]
    manifest = build_manifest(workspace)
    assert "DemoPage" in manifest.get("pages", {})
    assert manifest.get("content_hash")
    session_link = manifest["pages"]["DemoPage"]["locators"]["session_github_link"]["expression"]
    assert '"SeleniumBase on GitHub"' in session_link
    assert "'SeleniumBase on GitHub'" not in session_link


def test_extract_property_return_expression_preserves_source_quotes():
    from healing.locator_source import extract_property_return_expression

    source = '''class DemoPage:
    @property
    def session_github_link(self) -> Locator:
        """Team demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("link", name="WRONG_GITHUB_LINK_DEMO")
'''
    expr = extract_property_return_expression(source, "session_github_link")
    assert expr == 'self.page.get_by_role("link", name="WRONG_GITHUB_LINK_DEMO")'


def test_write_stub_patch_uses_exact_source_expression(tmp_path: Path, monkeypatch):
    from healing.pom_propose import write_stub_patch

    monkeypatch.chdir(tmp_path)
    ensure_queue_dirs()
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page_file = pages_dir / "demo_page.py"
    page_file.write_text(
        '''class DemoPage:
    @property
    def healing_demo_green_button(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("button", name="Click Me (Blue)")
''',
        encoding="utf-8",
    )
    manifest = {
        "pages": {
            "DemoPage": {
                "file": str(page_file),
                "locators": {
                    "healing_demo_green_button": {
                        "line": 3,
                        "expression": "self.page.get_by_role('button', name='Click Me (Blue)')",
                    }
                },
            }
        }
    }
    failure = {
        "failure_id": "F-stubexpr01",
        "architecture_ref": "DemoPage.healing_demo_green_button",
        "test": {"file": "tests/test_healing_flow_demo.py"},
    }
    patch_id, json_path, _ = write_stub_patch(failure, manifest=manifest, workspace=tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    before = payload["proposal"]["architecture_updates"][0]["before"]
    assert before == 'self.page.get_by_role("button", name="Click Me (Blue)")'
    assert patch_id.startswith("P-")


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
    assert index["entries"][0]["status"] == "awaiting_agent"


def test_mark_patch_ready_promotes_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_queue_dirs()
    failure_id = "F-testpatch01"
    patch_id = "P-testpatch01"
    payload = {
        "failure_id": failure_id,
        "processed": False,
        "test": {"nodeid": "t", "file": "tests/t.py", "name": "t"},
        "error": {"type": "TimeoutError", "message": "locator timeout"},
        "architecture_ref": "DemoPage.green_button",
        "failing_step": {"locator_id": "green_button"},
    }
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    md_path.write_text("# fail", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)

    patch_json = tmp_path / "artifacts/healing-queue/patches" / f"{patch_id}.json"
    patch_json.parent.mkdir(parents=True, exist_ok=True)
    patch_json.write_text(
        json.dumps(
            {
                "proposal": {
                    "patch_id": patch_id,
                    "failure_id": failure_id,
                    "proposal_status": "complete",
                    "architecture_updates": [
                        {
                            "file": "pages/demo_page.py",
                            "symbol": "green_button",
                            "before": "return self.page.get_by_role('button', name='old')",
                            "after": "return self.page.get_by_role('button', name='new')",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    patch_md = patch_json.with_suffix(".md")
    patch_md.write_text("# patch", encoding="utf-8")
    mark_failure_proposed(failure_id, patch_id, patch_json=patch_json, patch_md=patch_md)
    mark_patch_ready(patch_id)
    index = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    assert index["entries"][0]["status"] == "patch_ready"


def test_failure_classifier_selector_break():
    payload = {
        "architecture_ref": "DemoPage.green_button",
        "failing_step": {"locator_id": "green_button"},
        "error": {"type": "TimeoutError", "message": "Locator.click: Timeout 3000ms exceeded."},
    }
    assert classify_failure(payload) == "selector_break"
    assert is_healable(payload)


def test_failure_classifier_network():
    payload = {
        "architecture_ref": None,
        "error": {"type": "Error", "message": "net::ERR_INTERNET_DISCONNECTED"},
    }
    assert classify_failure(payload) == "network"
    assert not is_healable(payload)


def test_is_patch_complete_rejects_todo():
    assert not is_patch_complete(
        {
            "proposal_status": "awaiting_agent",
            "architecture_updates": [{"after": "TODO: replace with MCP-verified Playwright expression"}],
        }
    )
    assert is_patch_complete(
        {
            "proposal_status": "complete",
            "architecture_updates": [{"after": "return self.page.get_by_role('button', name='Go')"}],
        }
    )
    assert is_patch_complete(
        {
            "proposal_status": "awaiting_agent",
            "architecture_updates": [
                {"after": "return self.page.get_by_role('button', name='Click Me (Green)')"}
            ],
        }
    )


def test_promote_patch_skill_path_parity(tmp_path: Path, monkeypatch):
    from healing.patch_promote import promote_patch

    monkeypatch.chdir(tmp_path)
    ensure_queue_dirs()
    failure_id = "F-promote01"
    patch_id = "P-promote01"
    payload = {
        "failure_id": failure_id,
        "processed": False,
        "test": {"nodeid": "t", "file": "tests/t.py", "name": "t"},
        "error": {"type": "TimeoutError", "message": "locator timeout"},
        "architecture_ref": "DemoPage.healing_demo_green_button",
        "failing_step": {"locator_id": "healing_demo_green_button"},
    }
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    md_path.write_text("# fail", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)

    patch_json = tmp_path / "artifacts/healing-queue/patches" / f"{patch_id}.json"
    patch_json.parent.mkdir(parents=True, exist_ok=True)
    patch_json.write_text(
        json.dumps(
            {
                "proposal": {
                    "patch_id": patch_id,
                    "failure_id": failure_id,
                    "proposal_status": "awaiting_agent",
                    "architecture_updates": [
                        {
                            "file": "pages/demo_page.py",
                            "symbol": "healing_demo_green_button",
                            "before": "return self.page.get_by_role('button', name='Click Me (Blue)')",
                            "after": "return self.page.get_by_role('button', name='Click Me (Green)')",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    patch_md = patch_json.with_suffix(".md")
    patch_md.write_text("# patch", encoding="utf-8")
    mark_failure_proposed(failure_id, patch_id, patch_json=patch_json, patch_md=patch_md)

    promote_patch(patch_id)
    index = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
    assert index["entries"][0]["status"] == "patch_ready"
    saved = json.loads(patch_json.read_text(encoding="utf-8"))
    assert saved["proposal"]["proposal_status"] == "complete"


def test_ci_gates_skip_queue_gates(tmp_path: Path, monkeypatch):
    from healing.ci_gates import GateConfig, run_ci_gates

    monkeypatch.chdir(tmp_path)
    ensure_queue_dirs()
    failure_id = "F-gate001"
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

    config = GateConfig(max_unprocessed_failures=0, test_policy_enabled=False, require_architecture_manifest=False)
    exit_code, errors, _ = run_ci_gates(
        workspace=tmp_path,
        config=config,
        reports_dir=tmp_path / "artifacts" / "healing-reports",
        registry_path=tmp_path / "locator_registry.yaml",
        tests_dir=tmp_path / "tests",
        skip_queue_gates=True,
    )
    assert exit_code == 0
    assert not any("Unprocessed failures" in e for e in errors)

    exit_code, errors, _ = run_ci_gates(
        workspace=tmp_path,
        config=config,
        reports_dir=tmp_path / "artifacts" / "healing-reports",
        registry_path=tmp_path / "locator_registry.yaml",
        tests_dir=tmp_path / "tests",
        skip_queue_gates=False,
    )
    assert exit_code == 1
    assert any("Unprocessed failures" in e for e in errors)


def test_session_state_reset_and_note():
    from healing.session_state import (
        note_healable_failure,
        reset_session_state,
        session_had_healable_failures,
    )

    reset_session_state()
    assert not session_had_healable_failures()
    note_healable_failure()
    assert session_had_healable_failures()
    reset_session_state()
    assert not session_had_healable_failures()


def test_should_run_post_test_chain_gating(tmp_path: Path, monkeypatch):
    from healing.post_test import should_run_post_test_chain
    from healing.session_state import note_healable_failure, reset_session_state

    reset_session_state()
    monkeypatch.delenv("HEALING_MCP_AUTO", raising=False)
    assert not should_run_post_test_chain(tmp_path)

    monkeypatch.setenv("HEALING_MCP_AUTO", "1")
    assert not should_run_post_test_chain(tmp_path)

    note_healable_failure()
    assert should_run_post_test_chain(tmp_path)

    reset_session_state()
    assert not should_run_post_test_chain(tmp_path)
