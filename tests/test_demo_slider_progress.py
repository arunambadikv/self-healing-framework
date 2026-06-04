def test_slider_control_visible(demo):
    demo.goto()
    demo.expect_slider_visible()


def test_progress_bar_visible(demo):
    demo.goto()
    demo.expect_progress_bar_visible()
