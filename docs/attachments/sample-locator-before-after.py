# pages/orangehrm_login_page.py — excerpt

# BEFORE (intentionally broken healing demo)
@property
def pomhealer_demo_login_button(self) -> Locator:
    """Healing demo: intentionally broken until MCP repair."""
    return self.page.get_by_role("button", name="Sign In")


# AFTER (applied via pomhealer-review --decision heal)
@property
def pomhealer_demo_login_button(self) -> Locator:
    """Healing demo: intentionally broken until MCP repair."""
    return self.page.get_by_role("button", name="Login")
