"""Team demo: pure Playwright (no `smart` fixture) — triggers raw learning on teardown."""

from playwright.sync_api import expect


def test_raw_green_button_and_text(page, base_url):
    page.goto(base_url)
    page.get_by_role("button", name="Click Me (Green)", exact=True).click()
    expect(page.locator("#pText")).to_be_visible()
