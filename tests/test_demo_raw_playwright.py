"""Legacy-style test using page fixture only — still uses DemoPage (no inline selectors)."""


def test_raw_green_button_and_text(page, base_url):
    from pages.demo_page import DemoPage

    demo = DemoPage(page, base_url)
    demo.goto()
    demo.click_green_button()
    demo.expect_green_text_visible()
