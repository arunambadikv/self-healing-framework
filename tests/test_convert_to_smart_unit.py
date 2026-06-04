"""Unit tests for raw → smart conversion (no browser)."""

from pathlib import Path

from healing.convert_to_smart import convert_file

_RAW_SAMPLE = """
def test_sample(page, base_url):
    page.get_by_role("button", name="Click Me (Green)", exact=True).click()
    expect(page.locator("#pText")).to_be_visible()
"""


def test_converts_get_by_role_with_exact_and_css_expect(tmp_path: Path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
demo.green_button:
  action: click
  preferred:
    - type: role
      role: button
      name: Click Me (Green)
demo.green_text:
  action: expect_visible
  preferred:
    - type: css
      value: "#pText"
""".strip(),
        encoding="utf-8",
    )
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(_RAW_SAMPLE.strip() + "\n", encoding="utf-8")

    converted, replacements = convert_file(registry_path=registry, test_file=test_file)
    body = "\n".join(converted)
    assert 'smart.click("demo.green_button")' in body
    assert 'smart.expect_visible("demo.green_text")' in body
    assert "smart" in body.split("def test_sample")[1].split(")")[0]
    assert len(replacements) == 2
