def test_checkboxes_radios(demo):
    demo.goto()
    demo.check_radio_1()
    demo.check_radio_2()
    demo.check_main_checkbox()
    demo.uncheck_precheck_box()
    demo.check_checkbox_1()
    demo.check_checkbox_2()
    demo.check_checkbox_3()
