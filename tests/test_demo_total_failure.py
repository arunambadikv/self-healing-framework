import pytest


@pytest.mark.demo_session
def test_session_github_link_total_failure(demo):
    demo.goto()
    demo.expect_session_github_link_visible()
