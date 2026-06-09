"""SeleniumBase demo page — all locators live here (Python-only POM)."""

from __future__ import annotations

from playwright.sync_api import FrameLocator, Locator, Page

from pages.base_page import BasePage


class DemoPage(BasePage):
    # --- Locator properties ---

    @property
    def text_input(self) -> Locator:
        return self.page.locator("#myTextInput")

    @property
    def textarea(self) -> Locator:
        return self.page.locator("#myTextarea")

    @property
    def prefilled_text(self) -> Locator:
        return self.page.locator("#myTextInput2")

    @property
    def placeholder_input(self) -> Locator:
        return self.page.get_by_placeholder("Placeholder Text Field")

    @property
    def readonly_input(self) -> Locator:
        return self.page.locator("#readOnlyText")

    @property
    def green_button(self) -> Locator:
        return self.page.get_by_role("button", name="Click Me (Green)")

    @property
    def healing_demo_green_button(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("button", name="Click Me (Blue)")

    @property
    def paragraph_text(self) -> Locator:
        return self.page.get_by_text("Paragraph with Text:")

    @property
    def green_text(self) -> Locator:
        return self.page.locator("#pText")

    @property
    def seleniumbase_link(self) -> Locator:
        return self.page.get_by_role("link", name="seleniumbase.com")

    @property
    def github_link(self) -> Locator:
        return self.page.get_by_role("link", name="SeleniumBase on GitHub")

    @property
    def docs_link(self) -> Locator:
        return self.page.get_by_role("link", name="seleniumbase.io")

    @property
    def session_github_link(self) -> Locator:
        """Team demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("link", name="WRONG_GITHUB_LINK_DEMO")

    @property
    def select_dropdown(self) -> Locator:
        return self.page.get_by_role("combobox")

    @property
    def meter(self) -> Locator:
        return self.page.get_by_role("meter")

    @property
    def slider(self) -> Locator:
        return self.page.locator("#mySlider")

    @property
    def progress_bar(self) -> Locator:
        return self.page.locator("#progressBar")

    @property
    def radio_1(self) -> Locator:
        return self.page.locator("#radioButton1")

    @property
    def radio_2(self) -> Locator:
        return self.page.locator("#radioButton2")

    @property
    def checkbox(self) -> Locator:
        return self.page.locator("#checkBox1")

    @property
    def precheck_box(self) -> Locator:
        return self.page.locator("#checkBox5")

    @property
    def checkbox_1(self) -> Locator:
        return self.page.locator("#checkBox2")

    @property
    def checkbox_2(self) -> Locator:
        return self.page.locator("#checkBox3")

    @property
    def checkbox_3(self) -> Locator:
        return self.page.locator("#checkBox4")

    @property
    def iframe_1(self) -> FrameLocator:
        return self.page.frame_locator("#myFrame1")

    @property
    def iframe_3(self) -> FrameLocator:
        return self.page.frame_locator("#myFrame3")

    @property
    def iframe_image(self) -> Locator:
        return self.iframe_1.locator("img")

    @property
    def iframe_checkbox(self) -> Locator:
        return self.iframe_3.locator("#checkBox6")

    @property
    def drag_a(self) -> Locator:
        return self.page.locator("#logo")

    @property
    def drop_b(self) -> Locator:
        return self.page.locator("#drop2")

    # --- Interaction methods ---

    def fill_text_input(self, value: str) -> None:
        self._fill_locator("fill_text_input", "text_input", self.text_input, value)

    def fill_textarea(self, value: str) -> None:
        self._fill_locator("fill_textarea", "textarea", self.textarea, value)

    def fill_prefilled_text(self, value: str) -> None:
        self._fill_locator("fill_prefilled_text", "prefilled_text", self.prefilled_text, value)

    def fill_placeholder_input(self, value: str) -> None:
        self._fill_locator(
            "fill_placeholder_input", "placeholder_input", self.placeholder_input, value
        )

    def expect_readonly_input_visible(self) -> None:
        self._expect_visible("expect_readonly_input_visible", "readonly_input", self.readonly_input)

    def click_green_button(self) -> None:
        self._click_locator("click_green_button", "green_button", self.green_button)

    def click_healing_demo_green_button(self) -> None:
        self._click_locator(
            "click_healing_demo_green_button",
            "healing_demo_green_button",
            self.healing_demo_green_button,
        )

    def expect_paragraph_text_visible(self) -> None:
        self._expect_visible("expect_paragraph_text_visible", "paragraph_text", self.paragraph_text)

    def expect_green_text_visible(self) -> None:
        self._expect_visible("expect_green_text_visible", "green_text", self.green_text)

    def expect_seleniumbase_link_visible(self) -> None:
        self._expect_visible(
            "expect_seleniumbase_link_visible", "seleniumbase_link", self.seleniumbase_link
        )

    def expect_github_link_visible(self) -> None:
        self._expect_visible("expect_github_link_visible", "github_link", self.github_link)

    def expect_docs_link_visible(self) -> None:
        self._expect_visible("expect_docs_link_visible", "docs_link", self.docs_link)

    def expect_session_github_link_visible(self) -> None:
        self._expect_visible(
            "expect_session_github_link_visible",
            "session_github_link",
            self.session_github_link,
        )

    def select_dropdown_value(self, value: str) -> None:
        self._select_locator("select_dropdown_value", "select_dropdown", self.select_dropdown, value)

    def expect_meter_visible(self) -> None:
        self._expect_visible("expect_meter_visible", "meter", self.meter)

    def expect_slider_visible(self) -> None:
        self._expect_visible("expect_slider_visible", "slider", self.slider)

    def expect_progress_bar_visible(self) -> None:
        self._expect_visible("expect_progress_bar_visible", "progress_bar", self.progress_bar)

    def check_radio_1(self) -> None:
        self._check_locator("check_radio_1", "radio_1", self.radio_1)

    def check_radio_2(self) -> None:
        self._check_locator("check_radio_2", "radio_2", self.radio_2)

    def check_main_checkbox(self) -> None:
        self._check_locator("check_main_checkbox", "checkbox", self.checkbox)

    def uncheck_precheck_box(self) -> None:
        self._uncheck_locator("uncheck_precheck_box", "precheck_box", self.precheck_box)

    def check_checkbox_1(self) -> None:
        self._check_locator("check_checkbox_1", "checkbox_1", self.checkbox_1)

    def check_checkbox_2(self) -> None:
        self._check_locator("check_checkbox_2", "checkbox_2", self.checkbox_2)

    def check_checkbox_3(self) -> None:
        self._check_locator("check_checkbox_3", "checkbox_3", self.checkbox_3)

    def expect_iframe_image_visible(self) -> None:
        self._expect_visible("expect_iframe_image_visible", "iframe_image", self.iframe_image)

    def check_iframe_checkbox(self) -> None:
        self._check_locator("check_iframe_checkbox", "iframe_checkbox", self.iframe_checkbox)

    def drag_logo_to_drop_b(self) -> None:
        self._drag_to("drag_logo_to_drop_b", "drag_a", "drop_b", self.drag_a, self.drop_b)
