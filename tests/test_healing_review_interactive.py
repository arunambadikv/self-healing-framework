"""Tests for healing review display and interactive session."""

import json
from io import StringIO
from pathlib import Path

from healing.healing_queue import mark_failure_proposed, mark_patch_ready, register_failure
from healing.paths import configure_workspace, ensure_queue_dirs, FAILURES_DIR, QUEUE_PATCHES
from healing.review_display import format_patch_list, format_review_card, format_menu
from healing.review_interactive import run_interactive_review


def _seed_patch_ready(tmp_path: Path, monkeypatch, *, patch_id: str, failure_id: str) -> None:
    monkeypatch.chdir(tmp_path)
    configure_workspace(tmp_path)
    ensure_queue_dirs()
    pages = tmp_path / "pages"
    pages.mkdir(exist_ok=True)
    (pages / "demo_page.py").write_text(
        "class DemoPage:\n"
        "    @property\n"
        "    def green_button(self):\n"
        '        return self.page.get_by_role("button", name="Old")\n',
        encoding="utf-8",
    )
    failure_payload = {
        "failure_id": failure_id,
        "processed": False,
        "architecture_ref": "DemoPage.green_button",
        "environment": {"page_url": "https://example.com/demo"},
        "test": {"nodeid": "tests/test_demo.py::test_green_button[chromium]"},
        "error": {"type": "TimeoutError", "message": "Locator.click: Timeout 3000ms exceeded."},
        "failing_step": {
            "page_class": "DemoPage",
            "method": "click_green_button",
            "action": "click",
            "locator_id": "green_button",
        },
    }
    json_path = FAILURES_DIR / f"{failure_id}.json"
    md_path = FAILURES_DIR / f"{failure_id}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(failure_payload), encoding="utf-8")
    md_path.write_text("# failure", encoding="utf-8")
    register_failure(failure_id, json_path=json_path, md_path=md_path)

    patch_json = QUEUE_PATCHES / f"{patch_id}.json"
    patch_json.parent.mkdir(parents=True, exist_ok=True)
    patch_json.write_text(
        json.dumps(
            {
                "proposal": {
                    "patch_id": patch_id,
                    "failure_id": failure_id,
                    "risk_level": "low",
                    "risk_reason": "Verified via MCP",
                    "classification": "selector_break",
                    "architecture_updates": [
                        {
                            "file": "pages/demo_page.py",
                            "symbol": "green_button",
                            "line": 34,
                            "before": 'self.page.get_by_role("button", name="Old")',
                            "after": 'self.page.get_by_role("button", name="Click Me (Green)")',
                        }
                    ],
                    "validation_command": "pytest tests/test_demo.py::test_green_button -q",
                    "proposal_status": "complete",
                }
            }
        ),
        encoding="utf-8",
    )
    (QUEUE_PATCHES / f"{patch_id}.md").write_text("# patch", encoding="utf-8")
    mark_failure_proposed(failure_id, patch_id, patch_json=patch_json, patch_md=patch_json.with_suffix(".md"))
    mark_patch_ready(patch_id)


def test_format_review_card_includes_context(tmp_path: Path, monkeypatch):
    patch_id = "P-reviewcard01"
    failure_id = "F-reviewcard01"
    _seed_patch_ready(tmp_path, monkeypatch, patch_id=patch_id, failure_id=failure_id)
    payload = json.loads((QUEUE_PATCHES / f"{patch_id}.json").read_text(encoding="utf-8"))
    card = format_review_card(patch_id, payload, workspace=tmp_path, index=1, total=1)
    assert "test_green_button" in card
    assert "DemoPage.green_button" in card
    assert "PROPOSED FIX" in card
    assert 'name="Click Me (Green)"' in card
    assert "pytest tests/test_demo.py::test_green_button -q" in card


def test_format_patch_list_table(tmp_path: Path, monkeypatch):
    _seed_patch_ready(tmp_path, monkeypatch, patch_id="P-list01", failure_id="F-list01")
    ready = [{"patch_id": "P-list01", "failure_id": "F-list01"}]
    listing = format_patch_list(ready, workspace=tmp_path)
    assert "P-list01" in listing
    assert "test_green_button" in listing
    assert "--interactive" in listing


def test_format_menu_high_risk_warning():
    menu = format_menu(high_risk=True)
    assert "HIGH RISK" in menu
    assert "[1] Heal" in menu


def test_interactive_defer_then_quit(tmp_path: Path, monkeypatch):
    _seed_patch_ready(tmp_path, monkeypatch, patch_id="P-inter01", failure_id="F-inter01")
    inputs = iter(["3"])
    output = StringIO()

    rc = run_interactive_review(
        tmp_path,
        input_fn=lambda _: next(inputs, "q"),
        output=output,
    )

    assert rc == 0
    text = output.getvalue()
    assert "Deferred P-inter01" in text
    assert "status → deferred" in text
    assert "deferred" in text.lower()
    assert "No patch_ready items left" in text or "list-deferred" in text


def test_format_review_card_includes_screenshot(tmp_path: Path, monkeypatch):
    patch_id = "P-shot01"
    failure_id = "F-shot01"
    _seed_patch_ready(tmp_path, monkeypatch, patch_id=patch_id, failure_id=failure_id)
    failure_path = FAILURES_DIR / f"{failure_id}.json"
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    shot = tmp_path / "healer-artifacts" / "failures" / f"screenshot-{failure_id}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"fake-png")
    failure["artifacts"] = {"screenshot": str(shot)}
    failure_path.write_text(json.dumps(failure), encoding="utf-8")
    payload = json.loads((QUEUE_PATCHES / f"{patch_id}.json").read_text(encoding="utf-8"))
    card = format_review_card(patch_id, payload, workspace=tmp_path, index=1, total=1)
    assert "Screenshot:" in card
    assert str(shot.resolve()) in card


def test_interactive_heal_flow(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page_file = pages_dir / "demo_page.py"
    page_file.write_text(
        '''class DemoPage:
    @property
    def green_button(self):
        return self.page.get_by_role("button", name="Old")
''',
        encoding="utf-8",
    )
    _seed_patch_ready(tmp_path, monkeypatch, patch_id="P-heal01", failure_id="F-heal01")
    payload = json.loads((QUEUE_PATCHES / "P-heal01.json").read_text(encoding="utf-8"))
    payload["proposal"]["architecture_updates"][0]["file"] = str(page_file)
    payload["proposal"]["validation_command"] = ""
    (QUEUE_PATCHES / "P-heal01.json").write_text(json.dumps(payload), encoding="utf-8")

    output = StringIO()
    rc = run_interactive_review(
        tmp_path,
        input_fn=lambda _: "1",
        output=output,
    )

    assert rc == 0
    assert 'name="Click Me (Green)"' in page_file.read_text(encoding="utf-8")
    assert "Healed P-heal01" in output.getvalue()
