#!/usr/bin/env python3
"""Reset intentionally broken demo locators after a healing review apply."""

from __future__ import annotations

import re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

# Values replace the expression after `return ` (do not include the `return` keyword).
DEMO_BREAKS: dict[Path, dict[str, str]] = {
    WORKSPACE / "pages/orangehrm_login_page.py": {
        "pomhealer_demo_login_button": 'self.page.get_by_role("button", name="Sign In")',
        "pomhealer_demo_username_input": 'self.page.get_by_role("textbox", name="User Name")',
    },
    WORKSPACE / "pages/orangehrm_dashboard_page.py": {
        "pomhealer_demo_dashboard_heading": 'self.page.get_by_role("heading", name="Home")',
        "pomhealer_demo_pim_link": 'self.page.get_by_role("link", name="Employee List")',
    },
    WORKSPACE / "pages/saucedemo_login_page.py": {
        "pomhealer_demo_login_button": 'self.page.get_by_role("button", name="Sign In")',
    },
    WORKSPACE / "pages/saucedemo_inventory_page.py": {
        "pomhealer_demo_add_backpack": 'self.page.get_by_role("button", name="Add Backpack")',
    },
}


def reset_demo_locators() -> list[str]:
    messages: list[str] = []

    for file_path, symbols in DEMO_BREAKS.items():
        if not file_path.exists():
            messages.append(f"[skip] missing {file_path.relative_to(WORKSPACE)}")
            continue
        content = file_path.read_text(encoding="utf-8")
        updated = content
        for symbol, return_expr in symbols.items():
            if symbol not in updated:
                messages.append(f"[skip] {file_path.name}: no property {symbol}")
                continue
            symbol_pattern = re.compile(
                rf"(@property\s+def\s+{re.escape(symbol)}\s*\([^)]*\)\s*->[^:]+:\s*"
                rf"(?:\n\s+\"\"\"[\s\S]*?\"\"\"\s*)?"
                rf"\n\s*return\s+)(.+)"
            )
            sym_match = symbol_pattern.search(updated)
            if not sym_match:
                messages.append(f"[skip] {file_path.name}: could not parse {symbol}")
                continue
            updated = updated[: sym_match.start(2)] + return_expr + updated[sym_match.end(2) :]
            messages.append(f"[ok] {file_path.relative_to(WORKSPACE)} → {symbol}")
        if updated != content:
            file_path.write_text(updated, encoding="utf-8")
    return messages


def main() -> int:
    for line in reset_demo_locators():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
