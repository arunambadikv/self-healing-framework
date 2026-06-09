"""Opt-in healing pipeline demos — intentionally broken locators for MCP repair."""

import pytest


@pytest.mark.healing_demo
def test_healing_demo_github_link(demo):
    demo.goto()
    demo.expect_session_github_link_visible()


@pytest.mark.healing_demo
def test_healing_demo_green_button(demo):
    demo.goto()
    demo.click_healing_demo_green_button()
