"""Unit tests for raw-learning capture (no browser)."""

from healing.raw_learning import observations_to_healing_report, registry_entry_from_observation
from healing.raw_recorder import RawObservation, RawObservationCollector, make_semantic_key


def test_make_semantic_key_from_role():
    key = make_semantic_key(
        "test_pure_playwright_example",
        "click",
        {"type": "role", "role": "button", "name": "Click Me (Green)"},
    )
    assert key.startswith("auto.")
    assert "click" in key


def test_observations_to_healing_report_for_mcp():
    collector = RawObservationCollector(
        test_name="test_sample[chromium]",
        test_module="test_sample",
    )
    obs = RawObservation(
        semantic_key="auto.sample.click_button",
        action="click",
        candidate={"type": "role", "role": "button", "name": "Go"},
        intent="click button 'Go'",
        test_name="test_sample[chromium]",
    )
    collector.observations.append(obs)

    report = observations_to_healing_report(collector)
    event = report["events"][0]
    assert event["details"]["classification"] == "add_semantic_key"
    assert event["details"]["source"] == "raw_learning"
    assert registry_entry_from_observation(obs)["action"] == "click"
