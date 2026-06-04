import pytest


@pytest.mark.optional
@pytest.mark.skip(reason="Drag drop is flaky on this public demo page")
def test_drag_drop(demo):
    demo.goto()
    demo.check_main_checkbox()
    demo.drag_logo_to_drop_b()
