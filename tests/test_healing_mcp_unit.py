"""Unit tests for healing MCP auto-trigger logic."""

from pathlib import Path

from healing.healing_mcp import is_healing_mcp_auto_enabled, should_generate_mcp_for_report


def test_should_generate_for_healed_summary(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HEALING_MCP_AUTO", raising=False)
    report = tmp_path / "report.json"
    report.write_text('{"events": [], "summary": {"healed": 1, "failed": 0}}', encoding="utf-8")
    assert should_generate_mcp_for_report(report, {"healed": 1, "failed": 0}) is True


def test_healing_mcp_disabled_by_env(monkeypatch):
    monkeypatch.setenv("HEALING_MCP_AUTO", "0")
    assert is_healing_mcp_auto_enabled(workspace=Path.cwd()) is False
