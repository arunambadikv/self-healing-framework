def test_buttons_links(demo):
    demo.goto()
    demo.click_green_button()
    demo.expect_paragraph_text_visible()
    demo.expect_green_text_visible()
    demo.expect_seleniumbase_link_visible()
    demo.expect_github_link_visible()
    demo.expect_docs_link_visible()
