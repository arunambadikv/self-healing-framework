def test_buttons_links(page, smart, base_url):
    page.goto(base_url)
    
    # This intentionally tests healing framework. 
    # Primary selector in registry is broken, so it will heal.
    smart.click("demo.green_button")
    
    smart.expect_visible("demo.paragraph_text")
    smart.expect_visible("demo.green_text")
    smart.expect_visible("demo.seleniumbase_link")
    smart.expect_visible("demo.github_link")
    smart.expect_visible("demo.docs_link")
