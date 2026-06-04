def test_pure_playwright_green_button(page, base_url, smart):
    page.goto(base_url)
    smart.click("auto.pure_playwright_example.click_button_click_me_green")
    smart.expect_visible("demo.green_text")
