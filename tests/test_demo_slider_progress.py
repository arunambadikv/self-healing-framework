def test_slider_control_visible(page, smart, base_url):
    page.goto(base_url)
    smart.expect_visible("demo.slider")


def test_progress_bar_visible(page, smart, base_url):
    page.goto(base_url)
    smart.expect_visible("demo.progress_bar")
