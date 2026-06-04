import pytest


@pytest.mark.optional
@pytest.mark.skip(reason="Drag drop is flaky on this public demo page")
def test_drag_drop(page, smart, base_url):
    page.goto(base_url)
    smart.drag_to("demo.drag_a", "demo.drop_b")
