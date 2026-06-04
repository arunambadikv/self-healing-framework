def test_iframe(demo):
    demo.goto()
    demo.expect_iframe_image_visible()
    demo.check_iframe_checkbox()
