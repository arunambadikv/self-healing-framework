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
from healing.paths import configure_workspace, ensure_queue_dirs, FAILURES_DIR, QUEUE_INDEX


def test_build_manifest_includes_demo_page(tmp_path: Path, monkeypatch):
    workspace = Path(__file__).resolve().parents[1]
    manifest = build_manifest(workspace)
    assert "DemoPage" in manifest.get("pages", {})
    assert "OrangeHrmLoginPage" in manifest.get("pages", {})
    assert manifest.get("content_hash")
    session_link = manifest["pages"]["DemoPage"]["locators"]["session_github_link"]["expression"]
    assert '"SeleniumBase on GitHub"' in session_link
    assert "'SeleniumBase on GitHub'" not in session_link
    orangehrm_tests = [
        t for t in manifest.get("tests", []) if str(t.get("file", "")).endswith("test_orangehrm_healing.py")
    ]
    assert orangehrm_tests
    assert any(
        call.startswith("orangehrm_login.")
        for call in orangehrm_tests[0].get("page_method_calls", [])
    )


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
    configure_workspace(tmp_path)
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
    configure_workspace(tmp_path)
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
    patch_json = tmp_path / "healer-artifacts/healing-queue/patches" / f"{patch_id}.json"
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
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def green_button(self):\n"
        "        return self.page.get_by_role('button', name='old')\n",
        encoding="utf-8",
    )
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

    patch_json = tmp_path / "healer-artifacts/healing-queue/patches" / f"{patch_id}.json"
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
                            "before": "self.page.get_by_role('button', name='old')",
                            "after": "self.page.get_by_role('button', name='new')",
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


def test_failure_classifier_chrome_error_page_is_network():
    payload = {
        "architecture_ref": "OrangeHrmLoginPage.goto",
        "failing_step": {"method": "goto", "action": "navigate"},
        "environment": {"page_url": "chrome-error://chromewebdata/"},
        "error": {"type": "Error", "message": "Page.goto: net::ERR_NETWORK_CHANGED"},
    }
    assert classify_failure(payload) == "network"
    assert not is_healable(payload)


def test_failure_classifier_goto_timeout_not_selector_break():
    payload = {
        "architecture_ref": "OrangeHrmLoginPage.goto",
        "failing_step": {"method": "goto", "action": "navigate", "locator_id": None},
        "environment": {"page_url": "https://example.com/login"},
        "error": {"type": "TimeoutError", "message": "page.goto: Timeout 30000ms exceeded."},
    }
    assert classify_failure(payload) == "timeout"
    assert not is_healable(payload)


def test_infer_architecture_from_consumer_traceback():
    from healing.failure_report import build_failure_payload, infer_architecture_from_traceback

    tb = '''File "/home/arun/healing-consumer-demo/pages/practice_page.py", line 19, in open_test_table_wrong
    self.page.locator(self.WRONG_TABLE_LINK).click()
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("#test-table-link")
'''
    inferred = infer_architecture_from_traceback(tb)
    assert inferred is not None
    assert inferred["architecture_ref"] == "PracticePage.open_test_table_wrong"
    assert inferred["locator_id"] == "open_test_table_wrong"

    payload = build_failure_payload(
        failure_id="F-test",
        test_nodeid="tests/test_practice.py::test_x",
        test_file="tests/test_practice.py",
        test_name="test_x",
        base_url="https://example.com",
        page_url="https://example.com/practice/",
        exception_type="TimeoutError",
        exception_message='Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting for locator("#test-table-link")\n',
        traceback_text=tb,
        step_trace=None,
    )
    assert payload["architecture_ref"] == "PracticePage.open_test_table_wrong"
    assert payload["failing_step"]["locator_id"] == "open_test_table_wrong"
    assert payload["classification"] == "selector_break"
    assert payload["healable"] is True


def test_failure_classifier_auth_failure_not_healable():
    payload = {
        "architecture_ref": "OrangeHrmDashboardPage.healing_demo_dashboard_heading",
        "failing_step": {
            "page_class": "OrangeHrmDashboardPage",
            "method": "expect_healing_demo_dashboard_visible",
            "locator_id": "healing_demo_dashboard_heading",
        },
        "environment": {
            "page_url": "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login",
        },
        "error": {"type": "TimeoutError", "message": "Locator timed out"},
    }
    assert classify_failure(payload) == "auth_failure"
    assert not is_healable(payload)


def test_is_patch_complete_rejects_todo():
    assert not is_patch_complete(
        {
            "proposal_status": "awaiting_agent",
            "architecture_updates": [{"after": "TODO: replace with MCP-verified Playwright expression"}],
        }
    )
    complete_update = {
        "file": "pages/demo_page.py",
        "symbol": "green_button",
        "before": "self.page.get_by_role('button', name='old')",
        "after": "self.page.get_by_role('button', name='Go')",
    }
    assert is_patch_complete(
        {
            "proposal_status": "complete",
            "architecture_updates": [complete_update],
        }
    )
    assert is_patch_complete(
        {
            "proposal_status": "awaiting_agent",
            "architecture_updates": [
                {
                    **complete_update,
                    "after": "self.page.get_by_role('button', name='Click Me (Green)')",
                }
            ],
        }
    )
    assert not is_patch_complete(
        {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "green_button",
                    "before": "self.page.get_by_role('button', name='old')",
                    "after": "TODO: still pending",
                }
            ],
        }
    )


def test_promote_patch_skill_path_parity(tmp_path: Path, monkeypatch):
    from healing.patch_promote import promote_patch

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def healing_demo_green_button(self):\n"
        "        return self.page.get_by_role('button', name='Click Me (Blue)')\n",
        encoding="utf-8",
    )
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

    patch_json = tmp_path / "healer-artifacts/healing-queue/patches" / f"{patch_id}.json"
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
                            "before": "self.page.get_by_role('button', name='Click Me (Blue)')",
                            "after": "self.page.get_by_role('button', name='Click Me (Green)')",
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
    configure_workspace(tmp_path)
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
        reports_dir=tmp_path / "healer-artifacts" / "healing-reports",
        tests_dir=tmp_path / "tests",
        skip_queue_gates=True,
    )
    assert exit_code == 0
    assert not any("Unprocessed failures" in e for e in errors)

    exit_code, errors, _ = run_ci_gates(
        workspace=tmp_path,
        config=config,
        reports_dir=tmp_path / "healer-artifacts" / "healing-reports",
        tests_dir=tmp_path / "tests",
        skip_queue_gates=False,
    )
    assert exit_code == 1
    assert any("Unprocessed failures" in e for e in errors)


def test_session_state_reset_and_note():
    from healing.session_state import (
        note_healable_failure,
        note_session_patch,
        reset_session_state,
        session_had_healable_failures,
        session_healable_failure_ids,
        session_new_patch_ids,
    )

    reset_session_state()
    assert not session_had_healable_failures()
    note_healable_failure("F-abc")
    assert session_had_healable_failures()
    assert session_healable_failure_ids() == frozenset({"F-abc"})
    note_session_patch("P-new1")
    assert session_new_patch_ids() == frozenset({"P-new1"})
    reset_session_state()
    assert not session_had_healable_failures()
    assert not session_new_patch_ids()


def test_should_run_post_test_chain_gating(tmp_path: Path, monkeypatch):
    from healing.post_test import should_run_post_test_chain
    from healing.session_state import note_healable_failure, reset_session_state

    reset_session_state()
    monkeypatch.delenv("HEALING_MCP_AUTO", raising=False)
    assert not should_run_post_test_chain(tmp_path)

    monkeypatch.setenv("HEALING_MCP_AUTO", "1")
    assert not should_run_post_test_chain(tmp_path)

    note_healable_failure("F-session1")
    assert should_run_post_test_chain(tmp_path)

    reset_session_state()
    assert not should_run_post_test_chain(tmp_path)


def test_healing_mcp_auto_reads_from_dotenv(tmp_path: Path, monkeypatch):
    from healing.post_test import is_auto_enabled
    from healing.paths import configure_workspace, reset_workspace

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HEALING_MCP_AUTO", raising=False)
    (tmp_path / ".env").write_text("HEALING_MCP_AUTO=1\n", encoding="utf-8")
    configure_workspace(tmp_path)
    assert is_auto_enabled(tmp_path) is True
    monkeypatch.delenv("HEALING_MCP_AUTO", raising=False)
    reset_workspace()


def test_auto_architecture_discovery_on_package_stamp_change(tmp_path: Path, monkeypatch):
    from healing.auto_scan import (
        run_auto_architecture_discovery,
        should_auto_architecture_discovery,
        write_package_version_stamp,
    )
    from healing.paths import configure_workspace, reset_workspace

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "login_page.py").write_text("class LoginPage:\n    pass\n", encoding="utf-8")

    should, reason = should_auto_architecture_discovery(tmp_path)
    assert should is True
    assert "install" in reason or "manifest" in reason or "updated" in reason

    result = run_auto_architecture_discovery(tmp_path, quiet=True)
    assert result["ran"] is True
    assert (tmp_path / "healer-artifacts" / "architecture" / "manifest.json").exists()

    should2, reason2 = should_auto_architecture_discovery(tmp_path)
    assert should2 is False
    assert "up to date" in reason2

    write_package_version_stamp("0.0.0-old")
    should3, reason3 = should_auto_architecture_discovery(tmp_path)
    assert should3 is True
    assert "updated" in reason3
    reset_workspace()


def test_auto_chain_mcp_runs_latest_session_patch(tmp_path: Path, monkeypatch, capsys):
    """Auto MCP runs newest session patches; ignores unrelated stale awaiting_agent."""
    from healing.post_test import run_mcp_propose_all
    from healing.session_state import note_session_patch, reset_session_state

    reset_session_state()
    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()

    calls: list[str] = []

    def fake_process(entry, *, workspace, api_key=None, config=None):
        calls.append(entry["patch_id"])
        return True

    monkeypatch.setattr("healing.mcp_propose_runner.process_patch_entry", fake_process)

    def fake_select():
        return [
            {"patch_id": "P-new", "failure_id": "F-new", "status": "awaiting_agent", "created_at": "2026-07-22T12:00:00+00:00"},
            {"patch_id": "P-stale", "failure_id": "F-old", "status": "awaiting_agent", "created_at": "2026-07-01T12:00:00+00:00"},
        ]

    monkeypatch.setattr("healing.healing_queue.select_latest_awaiting_patches", fake_select)
    monkeypatch.setattr(
        "healing.healing_queue.list_awaiting_agent",
        lambda: fake_select(),
    )

    assert run_mcp_propose_all(tmp_path) == 0
    assert calls == []
    assert "no session patches" in capsys.readouterr().out

    note_session_patch("P-new")
    assert run_mcp_propose_all(tmp_path) == 0
    assert calls == ["P-new"]


def test_build_agent_prompt_uses_workspace_relative_patch_path(tmp_path: Path, monkeypatch):
    from healing.mcp_propose_runner import build_agent_prompt
    from healing.paths import QUEUE_PATCHES, configure_workspace, ensure_queue_dirs

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    patch_id = "P-test123"
    (QUEUE_PATCHES / f"{patch_id}.json").write_text('{"proposal": {}}', encoding="utf-8")

    prompt = build_agent_prompt(
        {"patch_id": patch_id, "failure_id": "F-test"},
        tmp_path.resolve(),
    )

    assert "healer-artifacts/healing-queue/patches/P-test123.json" in prompt


def test_pom_propose_creates_new_patch_for_duplicate_architecture_ref(tmp_path: Path, monkeypatch):
    from healing.architecture_scan import build_manifest, write_manifest
    from healing.healing_queue import list_unprocessed_failures, register_failure
    from healing.paths import FAILURES_DIR, configure_workspace, ensure_queue_dirs
    from healing.pom_propose import process_failure_entry
    from healing.session_state import reset_session_state, session_new_patch_ids

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    reset_session_state()
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "orangehrm_login_page.py").write_text(
        '''from playwright.sync_api import Locator

class OrangeHrmLoginPage:
    @property
    def healing_demo_login_button(self) -> Locator:
        return self.page.get_by_role("button", name="Sign In")
''',
        encoding="utf-8",
    )
    write_manifest(build_manifest(tmp_path), tmp_path)

    arch_ref = "OrangeHrmLoginPage.healing_demo_login_button"

    def _write_failure(failure_id: str) -> None:
        payload = {
            "failure_id": failure_id,
            "processed": False,
            "healable": True,
            "classification": "selector_break",
            "architecture_ref": arch_ref,
            "failing_step": {
                "page_class": "OrangeHrmLoginPage",
                "method": "click_healing_demo_login",
                "action": "click",
                "locator_id": "healing_demo_login_button",
            },
            "environment": {"base_url": "https://example.com/login"},
            "test": {"file": "tests/test_orangehrm_healing.py", "nodeid": f"tests/t.py::t[{failure_id}]"},
            "error": {"type": "TimeoutError", "message": "timeout"},
        }
        json_path = FAILURES_DIR / f"{failure_id}.json"
        md_path = FAILURES_DIR / f"{failure_id}.md"
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        md_path.write_text("# failure", encoding="utf-8")
        register_failure(failure_id, json_path=json_path, md_path=md_path)

    _write_failure("F-first")
    patch_id_1 = process_failure_entry({"failure_id": "F-first"}, workspace=tmp_path)
    assert patch_id_1

    _write_failure("F-second")
    patch_id_2 = process_failure_entry({"failure_id": "F-second"}, workspace=tmp_path)
    assert patch_id_2
    assert patch_id_2 != patch_id_1
    assert list_unprocessed_failures() == []
    assert session_new_patch_ids() == frozenset({patch_id_1, patch_id_2})


def test_list_patch_ready_newest_first(tmp_path: Path, monkeypatch):
    from healing.healing_queue import list_patch_ready, register_failure
    from healing.paths import FAILURES_DIR, QUEUE_INDEX, configure_workspace, ensure_queue_dirs

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()

    def _add(failure_id: str, patch_id: str, created_at: str) -> None:
        json_path = FAILURES_DIR / f"{failure_id}.json"
        md_path = FAILURES_DIR / f"{failure_id}.md"
        json_path.write_text("{}", encoding="utf-8")
        md_path.write_text("# f", encoding="utf-8")
        register_failure(failure_id, json_path=json_path, md_path=md_path)
        index = json.loads(QUEUE_INDEX.read_text(encoding="utf-8"))
        for entry in index["entries"]:
            if entry["failure_id"] == failure_id:
                entry["patch_id"] = patch_id
                entry["status"] = "patch_ready"
                entry["created_at"] = created_at
        QUEUE_INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")

    _add("F-old", "P-old", "2026-07-01T00:00:00+00:00")
    _add("F-new", "P-new", "2026-07-22T00:00:00+00:00")
    ready = list_patch_ready()
    assert [e["patch_id"] for e in ready] == ["P-new", "P-old"]


def test_build_failure_payload_includes_storage_state():
    from healing.failure_report import build_failure_payload
    from healing.step_trace import StepTraceCollector

    collector = StepTraceCollector(test_name="t", test_module="m")
    payload = build_failure_payload(
        failure_id="F-storagetest",
        test_nodeid="tests/t.py::t",
        test_file="tests/t.py",
        test_name="t",
        base_url="https://example.com/login",
        page_url="https://example.com/dashboard",
        exception_type="TimeoutError",
        exception_message="timeout",
        traceback_text="TimeoutError",
        step_trace=collector,
        screenshot_path="/tmp/shot.png",
        storage_state_path="/tmp/storage-state-F-storagetest.json",
    )
    assert payload["artifacts"]["storage_state"] == "/tmp/storage-state-F-storagetest.json"
    assert payload["environment"]["page_url"] == "https://example.com/dashboard"
    md = __import__("healing.failure_report", fromlist=["write_failure_markdown"]).write_failure_markdown(
        payload
    )
    assert "storage_state" in md


def test_mcp_servers_include_isolated_storage_state(tmp_path: Path, monkeypatch):
    from healing.mcp_propose_runner import resolve_storage_state_path
    from healing.mcp_stdio import load_playwright_mcp_stdio, with_storage_state_args

    state = tmp_path / "storage-state-F-x.json"
    state.write_text("{}", encoding="utf-8")
    args = with_storage_state_args(["@playwright/mcp@latest"], state)
    assert "--isolated" in args
    assert any(a.startswith("--storage-state=") for a in args)

    failure = {"artifacts": {"storage_state": str(state)}}
    assert resolve_storage_state_path(failure, tmp_path) == state

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}}),
        encoding="utf-8",
    )
    cfg = load_playwright_mcp_stdio(tmp_path, storage_state=state)
    assert "--isolated" in cfg.args
    assert any(str(a).startswith("--storage-state=") for a in cfg.args)


def test_proposal_prompt_prefers_page_url_and_storage_state():
    from healing.pom_propose import build_proposal_prompt

    failure = {
        "failure_id": "F-prompt1",
        "architecture_ref": "OrangeHrmDashboardPage.healing_demo_pim_link",
        "test": {"nodeid": "tests/t.py::t"},
        "error": {"type": "TimeoutError", "message": "timeout"},
        "environment": {
            "base_url": "https://example.com/login",
            "page_url": "https://example.com/dashboard",
        },
        "artifacts": {"storage_state": "healer-artifacts/failures/storage-state-F-prompt1.json"},
        "test_steps": [
            {"index": 0, "page_class": "P", "method": "goto", "action": "navigate"},
            {"index": 1, "page_class": "P", "method": "click_pim", "action": "click"},
        ],
        "failing_step": {"index": 1, "method": "click_pim"},
    }
    prompt = build_proposal_prompt(
        failure,
        manifest={},
        base_url="https://example.com/login",
        patch_id="P-1",
    )
    assert "https://example.com/dashboard" in prompt
    assert "storage-state-F-prompt1.json" in prompt
    assert "Session restore" in prompt


def test_slugify_test_name_handles_nodeids_and_params():
    from healing.artifact_naming import slugify_test_name

    assert slugify_test_name("test_login[chromium]") == "test_login-chromium"
    assert slugify_test_name("tests/t.py::test_login[chromium]") == "test_login-chromium"
    assert slugify_test_name("test/weird name!") == "test-weird-name"
    assert slugify_test_name("") == "unknown"
    assert slugify_test_name(None) == "unknown"
    long = "a" * 80
    assert len(slugify_test_name(long)) <= 48


def test_new_failure_id_readable_format(tmp_path: Path, monkeypatch):
    from healing.failure_report import new_failure_id
    from healing.paths import configure_workspace, ensure_queue_dirs

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    fid = new_failure_id("test_orangehrm_broken_login_button")
    assert fid.startswith("F-test_orangehrm_broken_login_button-")
    parts = fid.split("-")
    assert len(parts) >= 4  # F, slug parts..., date, time


def test_new_patch_id_readable_format(tmp_path: Path, monkeypatch):
    from healing.pom_propose import new_patch_id
    from healing.paths import configure_workspace, ensure_queue_dirs

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pid = new_patch_id("test_orangehrm_broken_login_button")
    assert pid.startswith("P-test_orangehrm_broken_login_button-")


def test_artifact_id_dedupes_within_same_second(tmp_path: Path, monkeypatch):
    from healing.artifact_naming import build_artifact_id
    from healing.paths import configure_workspace, ensure_queue_dirs, FAILURES_DIR

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    stamp = "20260801-120000"
    first = build_artifact_id(
        "F",
        "test_login",
        directory=Path(str(FAILURES_DIR)),
        suffixes=(".json", ".md"),
        stamp=stamp,
    )
    (FAILURES_DIR / f"{first}.json").write_text("{}", encoding="utf-8")
    second = build_artifact_id(
        "F",
        "test_login",
        directory=Path(str(FAILURES_DIR)),
        suffixes=(".json", ".md"),
        stamp=stamp,
    )
    assert first == "F-test_login-20260801-120000"
    assert second == "F-test_login-20260801-120000-2"


def test_load_skill_text_falls_back_to_package(tmp_path: Path, monkeypatch):
    from healing.paths import configure_workspace, reset_workspace
    from healing.skill_paths import load_skill_text

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    # No .cursor/skills in tmp workspace — must use packaged templates
    text = load_skill_text("playwright-locator-repair")
    assert "Missing skill file" not in text
    assert "playwright" in text.lower() or "locator" in text.lower()
    reset_workspace()


def test_load_skill_text_prefers_workspace(tmp_path: Path, monkeypatch):
    from healing.paths import configure_workspace, reset_workspace
    from healing.skill_paths import load_skill_text

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    skill_dir = tmp_path / ".cursor" / "skills" / "playwright-locator-repair"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Workspace override skill\n", encoding="utf-8")
    text = load_skill_text("playwright-locator-repair")
    assert "Workspace override skill" in text
    reset_workspace()


def test_bundled_skills_match_cursor_skills():
    """Package templates must stay in sync with .cursor/skills/ (source of truth)."""
    from healing.skill_paths import BUNDLED_SKILLS

    repo = Path(__file__).resolve().parents[1]
    for name in BUNDLED_SKILLS:
        cursor = repo / ".cursor" / "skills" / name / "SKILL.md"
        tmpl = repo / "healing" / "templates" / "skills" / name / "SKILL.md"
        assert cursor.exists(), f"missing {cursor}"
        assert tmpl.exists(), f"missing {tmpl}"
        assert cursor.read_bytes() == tmpl.read_bytes(), f"drift: {name}"


def test_load_config_prefers_healer_artifacts_healing_toml(tmp_path: Path, monkeypatch):
    from healing.config import load_config, reset_config_cache
    from healing.paths import configure_workspace, reset_workspace

    monkeypatch.chdir(tmp_path)
    (tmp_path / "healing.toml").write_text('artifacts_dir = "root-artifacts"\n', encoding="utf-8")
    root = tmp_path / "healer-artifacts"
    root.mkdir()
    (root / "healing.toml").write_text(
        'artifacts_dir = "healer-artifacts"\nskills_dir = ".cursor/skills"\n',
        encoding="utf-8",
    )
    configure_workspace(tmp_path)
    reset_config_cache()
    cfg = load_config(tmp_path)
    assert cfg.artifacts_dir == "healer-artifacts"
    reset_workspace()


def test_init_workspace_writes_healer_layout_and_skills(tmp_path: Path, monkeypatch):
    from healing.init import init_workspace
    from healing.paths import FAILURES_DIR, reset_workspace

    monkeypatch.chdir(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "login_page.py").write_text(
        "class LoginPage:\n    pass\n",
        encoding="utf-8",
    )
    result = init_workspace(tmp_path, force=True, scan=True)
    assert result["healing_toml"] == "healer-artifacts/healing.toml"
    assert (tmp_path / "healer-artifacts" / "healing.toml").exists()
    assert result.get("env_example") == ".env.example"
    assert (tmp_path / ".env.example").exists()
    assert "CURSOR_API_KEY" in (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert "HEALING_LLM_PROVIDER" in (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert FAILURES_DIR.resolve() == (tmp_path / "healer-artifacts" / "failures").resolve()
    assert (tmp_path / ".cursor" / "skills" / "healing-init" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / "healer-artifacts" / "architecture" / "manifest.json").exists()
    reset_workspace()


def test_doctor_reports_ok_for_package_and_warns_without_api_key(tmp_path: Path, monkeypatch):
    from healing.doctor import run_doctor
    from healing.init import init_workspace
    from healing.paths import reset_workspace

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HEALING_LLM_PROVIDER", raising=False)
    init_workspace(tmp_path, force=True, scan=False)
    results = run_doctor(tmp_path, verify_mcp=False)
    by_name = {r.name: r for r in results}
    assert by_name["healing package"].status == "ok"
    assert by_name["LLM API key"].status == "warn"
    assert by_name["mcp.json"].status == "ok"
    assert by_name["healing.toml"].status == "ok"
    reset_workspace()


def test_load_dotenv_files_sets_api_key(tmp_path: Path, monkeypatch):
    from healing.doctor import load_dotenv_files

    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    (tmp_path / ".env").write_text("CURSOR_API_KEY=cursor_test_key\n", encoding="utf-8")
    loaded = load_dotenv_files(tmp_path)
    assert loaded
    import os

    assert os.environ.get("CURSOR_API_KEY") == "cursor_test_key"
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)


def test_find_chromium_executable_scans_cache(tmp_path: Path, monkeypatch):
    from healing.doctor import find_chromium_executable

    root = tmp_path / "ms-playwright" / "chromium-9999" / "chrome-linux64"
    root.mkdir(parents=True)
    chrome = root / "chrome"
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    chrome.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "ms-playwright"))
    found = find_chromium_executable()
    assert found == chrome


def test_patch_validate_rejects_todo_and_stale_before(tmp_path: Path, monkeypatch):
    from healing.patch_validate import validate_proposal

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def btn(self):\n"
        "        return self.page.get_by_role('button', name='live')\n",
        encoding="utf-8",
    )
    bad = validate_proposal(
        {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.get_by_role('button', name='stale')",
                    "after": "self.page.get_by_role('button', name='new')",
                }
            ]
        },
        workspace=tmp_path,
        check_source=True,
    )
    assert bad
    assert any("does not match" in e or "not found" in e for e in bad)
    todo_errs = validate_proposal(
        {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.get_by_role('button', name='live')",
                    "after": "TODO: fix me",
                }
            ]
        }
    )
    assert any("TODO" in e for e in todo_errs)
    ok = validate_proposal(
        {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.get_by_role('button', name='live')",
                    "after": "self.page.get_by_role('button', name='new')",
                }
            ]
        },
        workspace=tmp_path,
        check_source=True,
    )
    assert ok == []


def test_load_healing_yaml_falls_back_to_package(tmp_path: Path):
    from healing.gates_config import load_healing_yaml

    # No workspace healing/ci_gates_config.yaml
    data = load_healing_yaml(tmp_path)
    assert "thresholds" in data or "healing_mcp" in data or "test_policy" in data


def test_manifest_uses_relative_file_paths(tmp_path: Path, monkeypatch):
    from healing.architecture_scan import build_manifest

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def btn(self):\n"
        "        return self.page.locator('#x')\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_x(demo_page):\n    demo_page.btn.click()\n",
        encoding="utf-8",
    )
    manifest = build_manifest(tmp_path)
    page_file = manifest["pages"]["DemoPage"]["file"]
    assert page_file == "pages/demo_page.py"
    assert not page_file.startswith("/")
    test_file = manifest["tests"][0]["file"]
    assert test_file == "tests/test_demo.py"


def test_list_deferred_and_queue_lock_roundtrip(tmp_path: Path, monkeypatch):
    from healing.healing_queue import list_deferred, update_patch_status

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def green_button(self):\n"
        "        return self.page.get_by_role('button', name='old')\n",
        encoding="utf-8",
    )
    failure_id = "F-defer01"
    patch_id = "P-defer01"
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"failure_id": failure_id}), encoding="utf-8")
    md_path.write_text("# f", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)
    patch_json = tmp_path / "healer-artifacts/healing-queue/patches" / f"{patch_id}.json"
    patch_json.parent.mkdir(parents=True, exist_ok=True)
    patch_json.write_text(
        json.dumps(
            {
                "proposal": {
                    "architecture_updates": [
                        {
                            "file": "pages/demo_page.py",
                            "symbol": "green_button",
                            "before": "self.page.get_by_role('button', name='old')",
                            "after": "self.page.get_by_role('button', name='new')",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    patch_md = patch_json.with_suffix(".md")
    patch_md.write_text("# p", encoding="utf-8")
    mark_failure_proposed(failure_id, patch_id, patch_json=patch_json, patch_md=patch_md)
    mark_patch_ready(patch_id)
    update_patch_status(patch_id, "deferred", notes="later")
    deferred = list_deferred()
    assert any(e.get("patch_id") == patch_id for e in deferred)


def test_validation_command_allowlist():
    from healing.pom_apply import is_validation_command_allowed, parse_validation_command

    assert is_validation_command_allowed(["pytest", "tests/t.py", "-q"])
    assert is_validation_command_allowed(["python", "-m", "pytest", "tests/t.py"])
    assert is_validation_command_allowed(["python", "-m", "healing.ci_gates"])
    assert not is_validation_command_allowed(["bash", "-c", "rm -rf /"])
    assert not is_validation_command_allowed(["curl", "http://evil"])
    parse_validation_command("pytest tests/t.py -q")
    try:
        parse_validation_command("rm -rf /tmp/x")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "allowlisted" in str(exc)


def test_apply_patch_rolls_back_on_validation_failure(tmp_path: Path, monkeypatch):
    from healing.pom_apply import apply_patch_payload

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    page_file = pages / "demo_page.py"
    original = (
        "class DemoPage:\n"
        "    @property\n"
        "    def login_button(self):\n"
        '        return self.page.get_by_role("button", name="OLD")\n'
    )
    page_file.write_text(original, encoding="utf-8")
    payload = {
        "proposal": {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "login_button",
                    "before": 'self.page.get_by_role("button", name="OLD")',
                    "after": 'self.page.get_by_role("button", name="NEW")',
                }
            ],
            "validation_command": "pytest tests/does_not_exist_xyz.py -q",
        }
    }
    try:
        apply_patch_payload(payload, workspace=tmp_path, dry_run=False, run_validation=True)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "Validation failed" in str(exc)
    assert page_file.read_text(encoding="utf-8") == original


def test_apply_prefers_symbol_property_update(tmp_path: Path, monkeypatch):
    from healing.pom_apply import apply_patch_payload

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    pages = tmp_path / "pages"
    pages.mkdir()
    page_file = pages / "demo_page.py"
    page_file.write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def login_button(self):\n"
        '        return self.page.get_by_role("button", name="OLD")\n',
        encoding="utf-8",
    )
    payload = {
        "proposal": {
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "login_button",
                    "before": "WRONG_BEFORE_NOT_IN_FILE",
                    "after": 'self.page.get_by_role("button", name="NEW")',
                }
            ],
        }
    }
    messages = apply_patch_payload(
        payload, workspace=tmp_path, dry_run=False, run_validation=False
    )
    assert any("Updated property" in m for m in messages)
    assert 'name="NEW"' in page_file.read_text(encoding="utf-8")


def test_ci_gates_warn_mode_does_not_fail(tmp_path: Path, monkeypatch):
    from healing.ci_gates import GateConfig, run_ci_gates

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_raw.py").write_text(
        "def test_raw(page):\n    page.locator('#x').click()\n",
        encoding="utf-8",
    )
    config = GateConfig(
        test_policy_enabled=True,
        test_policy_raw_mode="warn",
        require_architecture_manifest=False,
        max_unprocessed_failures=999,
        require_pom_usage=False,
    )
    exit_code, errors, warnings = run_ci_gates(
        workspace=tmp_path,
        config=config,
        reports_dir=tmp_path / "healer-artifacts" / "healing-reports",
        tests_dir=tests_dir,
        skip_queue_gates=True,
    )
    assert exit_code == 0
    assert not errors
    assert warnings


def test_mocked_pipeline_capture_stub_promote_apply(tmp_path: Path, monkeypatch):
    """End-to-end without live MCP: register → stub → complete → promote → apply."""
    from healing.healing_queue import list_patch_ready
    from healing.patch_promote import promote_patch
    from healing.pom_apply import apply_patch_payload
    from healing.pom_propose import process_failure_entry
    from healing.paths import QUEUE_PATCHES

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    page_file = pages / "demo_page.py"
    page_file.write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def login_button(self):\n"
        '        return self.page.get_by_role("button", name="OLD")\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    failure_id = "F-pipe01"
    payload = {
        "failure_id": failure_id,
        "processed": False,
        "healable": True,
        "classification": "selector_break",
        "architecture_ref": "DemoPage.login_button",
        "test": {"nodeid": "tests/t.py::test_x", "file": "tests/t.py", "name": "test_x"},
        "error": {
            "type": "TimeoutError",
            "message": "Locator.click: Timeout",
            "playwright_hint": {"kind": "locator"},
        },
        "failing_step": {
            "page_class": "DemoPage",
            "locator_id": "login_button",
            "method": "click_login",
        },
        "environment": {"page_url": "https://example.com/login", "base_url": "https://example.com"},
    }
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    md_path.write_text("# fail", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)

    # Manifest for propose
    from healing.architecture_scan import build_manifest, write_manifest

    write_manifest(build_manifest(tmp_path), tmp_path)

    entry = list_unprocessed_failures()[0]
    patch_id = process_failure_entry(entry, workspace=tmp_path)
    assert patch_id

    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = patch["proposal"]
    update = proposal["architecture_updates"][0]
    update["after"] = 'self.page.get_by_role("button", name="NEW")'
    proposal["proposal_status"] = "complete"
    proposal["validation_command"] = "pytest -q --collect-only"
    patch_path.write_text(json.dumps(patch, indent=2), encoding="utf-8")

    promote_patch(patch_id)
    assert list_patch_ready()

    messages = apply_patch_payload(
        patch, workspace=tmp_path, dry_run=False, run_validation=False
    )
    assert any("Updated property" in m or "Replaced" in m for m in messages)
    assert 'name="NEW"' in page_file.read_text(encoding="utf-8")


def test_mcp_propose_runner_with_mocked_agent(tmp_path: Path, monkeypatch):
    import sys
    from types import ModuleType

    from healing.mcp_propose_runner import process_patch_entry
    from healing.paths import QUEUE_PATCHES

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def btn(self):\n"
        "        return self.page.locator('#old')\n",
        encoding="utf-8",
    )
    failure_id = "F-mcp01"
    patch_id = "P-mcp01"
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "failure_id": failure_id,
                "architecture_ref": "DemoPage.btn",
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    md_path.write_text("# f", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)

    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "proposal": {
            "patch_id": patch_id,
            "failure_id": failure_id,
            "proposal_status": "awaiting_agent",
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.locator('#old')",
                    "after": "TODO: replace",
                }
            ],
        }
    }
    patch_path.write_text(json.dumps(stub), encoding="utf-8")
    (QUEUE_PATCHES / f"{patch_id}.md").write_text("# task", encoding="utf-8")
    (QUEUE_PATCHES / f"{patch_id}-agent-task.md").write_text("# agent", encoding="utf-8")
    mark_failure_proposed(
        failure_id,
        patch_id,
        patch_json=patch_path,
        patch_md=QUEUE_PATCHES / f"{patch_id}.md",
    )

    def fake_prompt(prompt, options):
        data = json.loads(patch_path.read_text(encoding="utf-8"))
        data["proposal"]["architecture_updates"][0]["after"] = "self.page.locator('#new')"
        data["proposal"]["proposal_status"] = "complete"
        patch_path.write_text(json.dumps(data), encoding="utf-8")

        class Result:
            status = "ok"
            result = "done"

        return Result()

    class FakeAgent:
        prompt = staticmethod(fake_prompt)

    class FakeOptions:
        def __init__(self, **kwargs):
            pass

    class FakeLocal:
        def __init__(self, **kwargs):
            pass

    class FakeStdio:
        def __init__(self, **kwargs):
            pass

    fake_mod = ModuleType("cursor_sdk")
    fake_mod.Agent = FakeAgent
    fake_mod.AgentOptions = FakeOptions
    fake_mod.LocalAgentOptions = FakeLocal
    fake_mod.StdioMcpServerConfig = FakeStdio
    monkeypatch.setitem(sys.modules, "cursor_sdk", fake_mod)

    entry = {"patch_id": patch_id, "failure_id": failure_id}
    ok = process_patch_entry(entry, workspace=tmp_path, api_key="cursor_test")
    assert ok is True
    from healing.healing_queue import list_patch_ready

    assert any(e.get("patch_id") == patch_id for e in list_patch_ready())


def test_resolve_llm_config_defaults_and_keys(monkeypatch):
    from healing.llm_config import LlmConfigError, resolve_llm_config

    monkeypatch.delenv("HEALING_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HEALING_LLM_MODEL", raising=False)
    monkeypatch.delenv("HEALING_MCP_MODEL", raising=False)

    cfg = resolve_llm_config()
    assert cfg.provider == "cursor"
    assert cfg.model == "composer-2.5"
    assert not cfg.has_key

    monkeypatch.setenv("HEALING_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = resolve_llm_config(require_key=True)
    assert cfg.provider == "openai"
    assert cfg.api_key == "sk-test"
    assert cfg.model == "gpt-4.1"
    assert cfg.key_env == "OPENAI_API_KEY"

    monkeypatch.setenv("HEALING_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
    monkeypatch.setenv("HEALING_LLM_MODEL", "claude-custom")
    cfg = resolve_llm_config()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-custom"

    monkeypatch.setenv("HEALING_LLM_PROVIDER", "nope")
    try:
        resolve_llm_config()
        raise AssertionError("expected LlmConfigError")
    except LlmConfigError:
        pass


def test_openai_provider_mocked_tool_loop(tmp_path: Path, monkeypatch):
    """OpenAI provider completes a patch without live MCP/OpenAI (mocked loop)."""
    from healing.llm_config import LlmConfig
    from healing.mcp_propose_runner import process_patch_entry
    from healing.paths import QUEUE_PATCHES

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def btn(self):\n"
        "        return self.page.locator('#old')\n",
        encoding="utf-8",
    )
    failure_id = "F-oai01"
    patch_id = "P-oai01"
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"failure_id": failure_id, "artifacts": {}}), encoding="utf-8")
    md_path.write_text("# f", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)
    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "proposal": {
            "patch_id": patch_id,
            "failure_id": failure_id,
            "proposal_status": "awaiting_agent",
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.locator('#old')",
                    "after": "TODO: replace",
                }
            ],
        }
    }
    patch_path.write_text(json.dumps(stub), encoding="utf-8")
    (QUEUE_PATCHES / f"{patch_id}.md").write_text("# task", encoding="utf-8")
    mark_failure_proposed(
        failure_id, patch_id, patch_json=patch_path, patch_md=QUEUE_PATCHES / f"{patch_id}.md"
    )

    class FakeProvider:
        def run_propose(self, prompt, *, workspace, config, storage_state=None):
            data = json.loads(patch_path.read_text(encoding="utf-8"))
            data["proposal"]["architecture_updates"][0]["after"] = "self.page.locator('#new')"
            data["proposal"]["proposal_status"] = "complete"
            patch_path.write_text(json.dumps(data), encoding="utf-8")
            return "openai done"

    monkeypatch.setattr(
        "healing.propose_providers.get_provider",
        lambda cfg: FakeProvider(),
    )
    cfg = LlmConfig(provider="openai", api_key="sk-test", model="gpt-4.1", key_env="OPENAI_API_KEY")
    ok = process_patch_entry(
        {"patch_id": patch_id, "failure_id": failure_id},
        workspace=tmp_path,
        config=cfg,
    )
    assert ok is True
    from healing.healing_queue import list_patch_ready

    assert any(e.get("patch_id") == patch_id for e in list_patch_ready())


def test_anthropic_provider_mocked_tool_loop(tmp_path: Path, monkeypatch):
    from healing.llm_config import LlmConfig
    from healing.mcp_propose_runner import process_patch_entry
    from healing.paths import QUEUE_PATCHES

    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def btn(self):\n"
        "        return self.page.locator('#old')\n",
        encoding="utf-8",
    )
    failure_id = "F-ant01"
    patch_id = "P-ant01"
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({"failure_id": failure_id, "artifacts": {}}), encoding="utf-8")
    md_path.write_text("# f", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)
    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "proposal": {
            "patch_id": patch_id,
            "failure_id": failure_id,
            "proposal_status": "awaiting_agent",
            "architecture_updates": [
                {
                    "file": "pages/demo_page.py",
                    "symbol": "btn",
                    "before": "self.page.locator('#old')",
                    "after": "TODO: replace",
                }
            ],
        }
    }
    patch_path.write_text(json.dumps(stub), encoding="utf-8")
    (QUEUE_PATCHES / f"{patch_id}.md").write_text("# task", encoding="utf-8")
    mark_failure_proposed(
        failure_id, patch_id, patch_json=patch_path, patch_md=QUEUE_PATCHES / f"{patch_id}.md"
    )

    class FakeProvider:
        def run_propose(self, prompt, *, workspace, config, storage_state=None):
            data = json.loads(patch_path.read_text(encoding="utf-8"))
            data["proposal"]["architecture_updates"][0]["after"] = "self.page.locator('#new')"
            data["proposal"]["proposal_status"] = "complete"
            patch_path.write_text(json.dumps(data), encoding="utf-8")
            return "anthropic done"

    monkeypatch.setattr(
        "healing.propose_providers.get_provider",
        lambda cfg: FakeProvider(),
    )
    cfg = LlmConfig(
        provider="anthropic", api_key="ant-test", model="claude-sonnet-4-5", key_env="ANTHROPIC_API_KEY"
    )
    ok = process_patch_entry(
        {"patch_id": patch_id, "failure_id": failure_id},
        workspace=tmp_path,
        config=cfg,
    )
    assert ok is True


def test_ci_workflow_mentions_multi_provider_secrets():
    root = Path(__file__).resolve().parents[1]
    ci = (root / ".github/workflows/healing-ci.yml").read_text(encoding="utf-8")
    assert "HEALING_LLM_PROVIDER" in ci
    assert "OPENAI_API_KEY" in ci
    assert "ANTHROPIC_API_KEY" in ci
    e2e = (root / ".github/workflows/healing-pipeline-e2e.yml").read_text(encoding="utf-8")
    assert "HEALING_LLM_PROVIDER" in e2e
    assert "steps.llm.outputs.has_key" in e2e

