"""
🔐 Centralized Authentication Utility
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Handles Google Login and other OAuth flows across all platforms.
"""

import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException

def try_click(driver, element):
    """Try multiple methods to click an element."""
    try:
        element.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        pass
    return False

def google_login_flow(driver, platform_name, email):
    """
    Generic Google login flow. Looks for Google sign-in buttons 
    and handles the OAuth popup/redirect.
    """
    print(f"\n[{platform_name}] Checking for Google login...")
    
    # 1. Broad search for Google buttons
    google_btn = None
    google_selectors = [
        (By.XPATH, "//button[contains(text(),'Google')]"),
        (By.XPATH, "//a[contains(text(),'Google')]"),
        (By.XPATH, "//*[contains(text(),'Sign in with Google')]"),
        (By.XPATH, "//*[contains(text(),'Login with Google')]"),
        (By.XPATH, "//*[contains(text(),'Continue with Google')]"),
        (By.CSS_SELECTOR, "[data-provider='google'], .google-login, .google-btn"),
        (By.CSS_SELECTOR, "a[href*='google'], button[href*='google']"),
        (By.XPATH, "//img[contains(@src,'google')]//ancestor::a | //img[contains(@src,'google')]//ancestor::button"),
    ]

    for by, sel in google_selectors:
        try:
            btns = driver.find_elements(by, sel)
            for btn in btns:
                if btn.is_displayed():
                    text = (btn.text + " " + (btn.get_attribute("aria-label") or "")).lower()
                    if "google" in text or "google" in (btn.get_attribute("href") or ""):
                        google_btn = btn
                        break
            if google_btn: break
        except: continue

    if not google_btn:
        return False

    print(f"[{platform_name}] 🎯 Found Google login button, clicking...")
    try_click(driver, google_btn)
    time.sleep(3)

    # 2. Handle Google OAuth popup/redirect
    windows = driver.window_handles
    if len(windows) > 1:
        driver.switch_to.window(windows[-1])
        time.sleep(2)
        _handle_google_account_selection(driver, email, platform_name)
        try:
            if len(driver.window_handles) > 0:
                driver.switch_to.window(driver.window_handles[0])
        except: pass
    else:
        # Check if current page is Google login
        if "accounts.google.com" in driver.current_url:
            _handle_google_account_selection(driver, email, platform_name)
    
    time.sleep(3)
    return True

def _handle_google_account_selection(driver, email, platform_name):
    """Inner logic to select account or enter email in Google prompt."""
    try:
        # Try finding existing logged-in account
        accounts = driver.find_elements(By.CSS_SELECTOR, 
            "div[data-email], div[data-identifier], .account-name, div[role='link']")
        for acc in accounts:
            if email.lower() in acc.text.lower() or email.lower() in (acc.get_attribute("data-email") or "").lower():
                try_click(driver, acc)
                print(f"[{platform_name}] ✅ Selected existing Google account: {email}")
                return

        # Fallback: click first account if restricted
        if accounts:
            try_click(driver, accounts[0])
            print(f"[{platform_name}] ✅ Selected first available Google account")
            return

        # Fallback: enter email
        try:
            email_input = driver.find_element(By.CSS_SELECTOR, "input[type='email']")
            email_input.send_keys(email)
            email_input.send_keys(Keys.RETURN)
            time.sleep(3)
            print(f"[{platform_name}] 📧 Entered Google email, waiting for manual password/2FA...")
            time.sleep(10) # Give time for manual 2FA if needed
        except:
            print(f"[{platform_name}] ⏳ Google prompt detected. Please complete it manually if needed.")
    except Exception as e:
        print(f"[{platform_name}] ⚠️ Google flow error: {e}")
