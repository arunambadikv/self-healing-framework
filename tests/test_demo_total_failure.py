"""Team demo: all registry candidates fail → MCP + Cursor agent repairs registry."""

import pytest


@pytest.mark.demo_session
def test_session_github_link_total_failure(page, smart, base_url):
    page.goto(base_url)
    smart.expect_visible("demo.session_github_link")
