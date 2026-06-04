import os
import pytest
from pathlib import Path
from playwright.sync_api import Page

pytest_plugins = ["healing.pytest_plugin"]

from healing import load_registry, HealingReport, SmartPage
from healing.patcher import generate_registry_patch_markdown


def _registry_path() -> str:
    return os.environ.get("HEALING_REGISTRY_PATH", "locator_registry.yaml")


def _raw_learning_enabled() -> bool:
    return os.environ.get("HEALING_RAW_LEARNING", "1").strip() not in ("0", "false", "no")


@pytest.fixture(scope="session", autouse=True)
def _healing_install_raw_hooks():
    if not _raw_learning_enabled():
        return
    from healing.raw_recorder import install_locator_action_hooks

    install_locator_action_hooks()


@pytest.fixture(autouse=True)
def _healing_raw_learning(page: Page, request, base_url):
    """Transparently record raw Playwright actions when a test does not use `smart`."""
    if "smart" in request.fixturenames or not _raw_learning_enabled():
        yield
        return

    from healing.raw_learning import finalize_raw_learning
    from healing.raw_recorder import (
        RawObservationCollector,
        instrument_page,
        reset_collector,
        set_active_collector,
    )

    module_stem = Path(str(request.node.fspath)).stem
    collector = RawObservationCollector(
        test_name=request.node.name,
        test_module=module_stem,
    )
    token = set_active_collector(collector)
    instrument_page(page)
    yield
    reset_collector(token)

    if not collector.observations:
        return

    result = finalize_raw_learning(
        collector=collector,
        test_name=request.node.name,
        base_url=base_url,
    )
    print(
        f"\n[healing] raw-learning: captured {result['observation_count']} action(s); "
        f"draft={result['draft_path']}; mcp_bundles={result['mcp_bundles']}"
    )

@pytest.fixture(scope="session")
def base_url():
    return "https://seleniumbase.io/demo_page"

@pytest.fixture
def registry():
    return load_registry(_registry_path())

@pytest.fixture
def healing_report():
    return HealingReport()

@pytest.fixture
def smart(page: Page, registry, healing_report, request):
    smart_page = SmartPage(page, registry, healing_report)
    yield smart_page
    
    test_name = request.node.name
    report_path = Path("artifacts") / "healing-reports" / f"{test_name}.json"
    healing_report.save(str(report_path))

    patch_path = Path("artifacts") / "patch-suggestions" / f"{test_name}.md"
    generate_registry_patch_markdown(report_path, patch_path)

    summary = healing_report.summary
    mcp_count = 0
    if report_path.exists():
        from healing.healing_mcp import finalize_healing_mcp

        mcp_count = finalize_healing_mcp(
            report_path=report_path,
            base_url=request.getfixturevalue("base_url"),
            summary=summary,
            workspace=Path.cwd(),
        )
    if mcp_count:
        print(
            f"\n[healing] smart-healing MCP: generated {mcp_count} bundle(s) for "
            f"healed={summary.get('healed', 0)} failed={summary.get('failed', 0)} "
            f"→ artifacts/mcp-repair-bundles/prompts/"
        )
