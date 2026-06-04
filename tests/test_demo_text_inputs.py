def test_text_inputs(page, smart, base_url):
    page.goto(base_url)
    
    smart.fill("demo.text_input", "Hello Text")
    smart.fill("demo.textarea", "Hello Textarea")
    smart.fill("demo.prefilled_text", "Updated Text")
    smart.fill("demo.placeholder_input", "Custom Placeholder Text")
    
    smart.expect_visible("demo.readonly_input")
