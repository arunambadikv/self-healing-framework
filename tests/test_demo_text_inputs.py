def test_text_inputs(demo):
    demo.goto()
    demo.fill_text_input("Hello Text")
    demo.fill_textarea("Hello Textarea")
    demo.fill_prefilled_text("Updated Text")
    demo.fill_placeholder_input("Custom Placeholder Text")
    demo.expect_readonly_input_visible()
