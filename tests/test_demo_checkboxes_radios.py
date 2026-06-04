def test_checkboxes_radios(page, smart, base_url):
    page.goto(base_url)
    
    smart.check("demo.radio_1")
    smart.check("demo.radio_2")
    
    smart.check("demo.checkbox")
    smart.uncheck("demo.precheck_box")
    
    smart.check("demo.checkbox_1")
    smart.check("demo.checkbox_2")
    smart.check("demo.checkbox_3")
