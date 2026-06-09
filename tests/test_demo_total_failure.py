"""Deprecated: use tests/test_healing_flow_demo.py with --run-healing-demo."""

import pytest


@pytest.mark.demo_session
@pytest.mark.skip(
    reason="Deprecated: use tests/test_healing_flow_demo.py with --run-healing-demo"
)
def test_session_github_link_total_failure(demo):
    demo.goto()
    demo.expect_session_github_link_visible()
