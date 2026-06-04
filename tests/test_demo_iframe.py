def test_iframe(page, smart, base_url):
    page.goto(base_url)
    
    smart.expect_visible("demo.iframe_image")
    smart.check("demo.iframe_checkbox")
