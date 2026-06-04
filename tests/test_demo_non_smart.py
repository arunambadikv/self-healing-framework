def test_non_smart_raw_playwright_flow(page, base_url, smart):
    page.goto(base_url)

    smart.fill("demo.text_input", "Raw path input")
    smart.fill("demo.textarea", "Raw path textarea")
    smart.click("demo.green_button")

    smart.expect_visible("demo.green_text")
    smart.expect_visible("demo.github_link")
