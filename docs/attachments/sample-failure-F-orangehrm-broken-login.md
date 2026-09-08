# Failure Report: F-test_orangehrm_broken_login_button-20260804-123456

**When:** 2026-08-04T12:34:56+00:00  
**Test:** `tests/test_orangehrm_pomhealer.py::test_orangehrm_broken_login_button`  
**File:** `tests/test_orangehrm_pomhealer.py`

## What happened

- **Error:** `TimeoutError`: Locator.click: Timeout 30000ms exceeded.
  - waiting for `get_by_role("button", name="Sign In")`
- **URL:** https://opensource-demo.orangehrmlive.com/web/index.php/auth/login
- **Classification:** `selector_break` (healable)
- **architecture_ref:** `OrangeHrmLoginPage.pomhealer_demo_login_button`

## Test steps

| # | Page | Method | Action | Locator |
|---|------|--------|--------|---------|
| 0 | OrangeHrmLoginPage | goto | navigate | — |
| 1 | OrangeHrmLoginPage | fill_username | fill | username_input |
| 2 | OrangeHrmLoginPage | fill_password | fill | password_input |
| 3 | OrangeHrmLoginPage | click_pomhealer_demo_login | click | **pomhealer_demo_login_button** ← failing |

## Artifacts

- Screenshot: `screenshot-F-test_orangehrm_broken_login_button-20260804-123456.png`
- Storage state: `storage-state-F-….json`

## Status

- `processed`: false — next: `pomhealer-propose` / `POMHEALER_MCP_AUTO`
