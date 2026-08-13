# Architecture Manifest (excerpt)

**Generated:** 2026-08-04T10:38:36+00:00  
**Content hash:** `620a2ccaeb18f269`

## Pages

### OrangeHrmLoginPage (`pages/orangehrm_login_page.py`)

**Locators:**

- `username_input` (line 18): `self.page.get_by_role("textbox", name="Username")`
- `password_input` (line 22): `self.page.get_by_role("textbox", name="Password")`
- `login_button` (line 26): `self.page.get_by_role("button", name="Login")`
- `healing_demo_login_button` (line 30): `self.page.get_by_role("button", name="Sign In")` ← demo break

**Methods:**

- `fill_username` → username_input
- `fill_password` → password_input
- `click_login` → login_button
- `click_healing_demo_login` → healing_demo_login_button
