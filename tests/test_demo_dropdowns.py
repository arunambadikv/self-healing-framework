def test_dropdowns(page, smart, base_url):
    page.goto(base_url)

    smart.select_option("demo.select_dropdown", "75%")
    smart.expect_visible("demo.meter")

    smart.select_option("demo.set_25", "25%")
    smart.expect_visible("demo.meter")

    smart.select_option("demo.set_50", "50%")
    smart.expect_visible("demo.meter")

    smart.select_option("demo.set_75", "75%")
    smart.expect_visible("demo.meter")

    smart.select_option("demo.set_100", "100%")
    smart.expect_visible("demo.meter")
