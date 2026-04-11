import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException
)
import smart_form_filler
from utils.auth import google_login_flow
from agent_stop import should_stop


def try_click(driver, element):
    """Try multiple click methods."""
    try:
        element.click()
        return True
    except (ElementClickInterceptedException, Exception):
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        pass
    return False


def is_driver_alive(driver):
    """Check if the browser session is still usable."""
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def ensure_single_tab(driver):
    """Close all tabs except the first one and switch to it."""
    try:
        while len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            driver.close()
        driver.switch_to.window(driver.window_handles[0])
    except Exception:
        pass
    return True


def google_login_flow_wrapper(driver, platform_name, login_url, email):
    """Wrapper for centralized Google login flow."""
    print(f"\n[{platform_name}] Navigating to login page...")
    driver.get(login_url)
    time.sleep(3)
    return google_login_flow(driver, platform_name, email)


# ─────────────────────────────────────────────
#  UNSTOP
# ─────────────────────────────────────────────

def unstop_login(driver, email, password):
    """Login to Unstop via Google."""
    ok = google_login_flow_wrapper(driver, "Unstop", "https://unstop.com/auth/login", email)
    if ok:
        return True

    # Fallback: email/password
    print("[Unstop] Trying email/password login...")
    if password.startswith("YOUR_"):
        print("[Unstop] ❌ Password not set!")
        return False
    try:
        driver.find_element(By.NAME, "email").send_keys(email)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[contains(.,'Login') or @type='submit']").click()
        time.sleep(3)
        print("[Unstop] ✅ Logged in!")
        return True
    except Exception as e:
        print(f"[Unstop] ❌ Login failed: {e}")
        return False


def unstop_apply(driver, keywords, locations, max_jobs, applied_count,
                 config=None, dry_run=False, applied_urls=None):
    """
    Apply to internships on Unstop with smart form filling.
    Returns: (applied_count, list_of_new_urls)
    """
    if config is None:
        config = {}
    if applied_urls is None:
        applied_urls = set()

    new_urls = []

    for keyword in keywords:
        if should_stop():
            print("  ⏹  Stop requested — exiting agent early.")
            break
        if applied_count >= max_jobs:
            break

        keyword_applied = 0

        # Paginate through multiple pages
        for page in range(1, 4):  # Up to 3 pages
            if applied_count >= max_jobs:
                break

            # ── HEALTH CHECK ──
            if not is_driver_alive(driver):
                print("[Unstop] ❌ Browser died. Stopping.")
                return applied_count, new_urls

            search_url = (
                f"https://unstop.com/internships?"
                f"search={keyword.replace(' ', '%20')}"
                f"&oppstatus=open&page={page}"
            )
            print(f"\n[Unstop] 🔍 Searching: {keyword} (page {page})")
            driver.get(search_url)
            time.sleep(3)

            # Collect listing URLs
            cards = driver.find_elements(By.CSS_SELECTOR,
                "a.single_profile, a[href*='/internship/'], "
                "a[href*='/internships/'], .opp-card a, "
                ".opportunity-card a")
            urls = list(set([c.get_attribute("href") for c in cards if c.get_attribute("href")]))
            print(f"  Found {len(urls)} listings")

            if not urls:
                print("  ⚠️  No more listings. Moving to next keyword.")
                break

            for url in urls[:20]:
                if applied_count >= max_jobs:
                    break

                # ── DEDUP CHECK ──
                if url in applied_urls:
                    print(f"  [Skip] Already applied (dedup): {url[:60]}...")
                    continue

                # ── HEALTH CHECK ──
                if not is_driver_alive(driver):
                    print("[Unstop] ❌ Browser died mid-apply. Stopping.")
                    return applied_count, new_urls

                try:
                    # Step 1: Open in new tab
                    driver.execute_script(f"window.open('{url}', '_blank');")
                    time.sleep(2)
                    driver.switch_to.window(driver.window_handles[-1])
                    time.sleep(random.uniform(2, 3))

                    title = "Unknown"
                    try:
                        title = driver.find_element(By.CSS_SELECTOR,
                            "h1, .opportunity-heading, .opp-title").text.strip()[:60]
                    except:
                        pass

                    print(f"\n  📋 [{keyword_applied+1}] {title}")

                    # Step 2: Find apply/register button
                    try:
                        apply_btn = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable(
                                (By.XPATH,
                                 "//button[contains(.,'Apply') or contains(.,'Register') or "
                                 "contains(.,'Participate')]")
                            )
                        )
                        btn_text = apply_btn.text.strip().lower()
                        if "applied" in btn_text or "registered" in btn_text:
                            print(f"  ⏭️  Already applied on platform — skipping")
                            applied_urls.add(url)
                            new_urls.append(url)
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            continue

                        if dry_run:
                            print("  [DRY RUN] ✅ Would apply here")
                            applied_count += 1
                            keyword_applied += 1
                            new_urls.append(url)
                            applied_urls.add(url)
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            continue

                        # Step 3: Click Apply
                        print(f"  🎯 Clicking Apply...")
                        apply_btn.click()
                        time.sleep(2)

                        # Step 4: Fill form
                        print(f"  📝 Filling form...")
                        smart_form_filler.fill_all_form_fields(driver, config)
                        time.sleep(1)

                        # Step 5: Try confirm/submit buttons
                        submitted = False
                        for btn_label in ["Confirm", "Submit", "Apply", "Register", "Proceed"]:
                            try:
                                confirm = driver.find_element(
                                    By.XPATH, f"//button[contains(.,'{btn_label}')]")
                                if confirm.is_displayed() and confirm.is_enabled():
                                    confirm.click()
                                    time.sleep(2)
                                    submitted = True
                                    break
                            except:
                                continue

                        if not submitted:
                            # Try multi-step form
                            result = smart_form_filler.walk_multi_step_form(driver, config, max_steps=6)
                            submitted = result == "submitted"

                        if submitted:
                            print(f"  ✅ Applied successfully!")
                            applied_count += 1
                            keyword_applied += 1
                            new_urls.append(url)
                            applied_urls.add(url)
                        else:
                            print(f"  ⚠️  Could not auto-submit — skipping")

                        # Step 6: Close tab
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except Exception:
                            pass

                    except TimeoutException:
                        print(f"  ⏭️  No apply button found — skipping")
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except Exception:
                            pass

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    ensure_single_tab(driver)

                time.sleep(random.uniform(3, 8))

        print(f"\n[Unstop] ✅ '{keyword}': Applied to {keyword_applied} jobs")

    print(f"\n[Unstop] 📊 Total applied: {applied_count} | New this session: {len(new_urls)}")
    return applied_count, new_urls


# ─────────────────────────────────────────────
#  NAUKRI
# ─────────────────────────────────────────────

def naukri_login(driver, email, password):
    """Login to Naukri via Google."""
    ok = google_login_flow_wrapper(driver, "Naukri", "https://www.naukri.com/nlogin/login", email)
    if ok:
        return True

    # Fallback: email/password
    print("[Naukri] Trying email/password login...")
    if password.startswith("YOUR_"):
        print("[Naukri] ❌ Password not set!")
        return False
    try:
        driver.find_element(By.ID, "usernameField").send_keys(email)
        driver.find_element(By.ID, "passwordField").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(4)
        print("[Naukri] ✅ Logged in!")
        return True
    except Exception as e:
        print(f"[Naukri] ❌ Login failed: {e}")
        return False


def naukri_apply(driver, keywords, locations, max_jobs, applied_count,
                 resume_path="", config=None, dry_run=False, applied_urls=None):
    """
    Apply to jobs on Naukri with smart form filling.
    Returns: (applied_count, list_of_new_urls)
    """
    if config is None:
        config = {}
    if applied_urls is None:
        applied_urls = set()

    new_urls = []

    for keyword in keywords:
        if should_stop():
            print("  ⏹  Stop requested — exiting agent early.")
            break
        if applied_count >= max_jobs:
            break

        keyword_applied = 0

        # Paginate through multiple pages
        for page in range(1, 4):  # Up to 3 pages
            if applied_count >= max_jobs:
                break

            # ── HEALTH CHECK ──
            if not is_driver_alive(driver):
                print("[Naukri] ❌ Browser died. Stopping.")
                return applied_count, new_urls

            search_url = (
                f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs-in-india"
                f"?jobAge=1&experience=0&jobType=internship&pageNo={page}"
            )

            print(f"\n[Naukri] 🔍 Searching: {keyword} (page {page})")
            driver.get(search_url)
            time.sleep(3)

            # Collect job URLs
            cards = driver.find_elements(By.CSS_SELECTOR,
                "article.jobTuple a.title, a[href*='/job-listings-'], "
                "a.title, .jobTupleHeader a, "
                "a[href*='naukri.com/job-listings']")
            urls = list(set([c.get_attribute("href") for c in cards if c.get_attribute("href")]))
            print(f"  Found {len(urls)} listings")

            if not urls:
                print("  ⚠️  No more listings. Moving to next keyword.")
                break

            for url in urls[:20]:
                if applied_count >= max_jobs:
                    break

                # ── DEDUP CHECK ──
                if url in applied_urls:
                    print(f"  [Skip] Already applied (dedup): {url[:60]}...")
                    continue

                # ── HEALTH CHECK ──
                if not is_driver_alive(driver):
                    print("[Naukri] ❌ Browser died mid-apply. Stopping.")
                    return applied_count, new_urls

                try:
                    # Step 1: Open in new tab
                    driver.execute_script(f"window.open('{url}', '_blank');")
                    time.sleep(2)
                    driver.switch_to.window(driver.window_handles[-1])
                    time.sleep(random.uniform(2, 3))

                    title = "Unknown"
                    try:
                        title = driver.find_element(By.CSS_SELECTOR,
                            "h1.jd-header-title, h1, .jd-header-title").text.strip()[:60]
                    except:
                        pass

                    print(f"\n  📋 [{keyword_applied+1}] {title}")

                    # Step 2: Find apply button
                    try:
                        apply_btn = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable(
                                (By.XPATH,
                                 "//button[contains(.,'Apply')] | "
                                 "//button[contains(@class,'apply-button')] | "
                                 "//a[contains(.,'Apply')]")
                            )
                        )

                        btn_text = apply_btn.text.strip().lower()
                        if "applied" in btn_text:
                            print(f"  ⏭️  Already applied on platform — skipping")
                            applied_urls.add(url)
                            new_urls.append(url)
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            continue

                        if dry_run:
                            print("  [DRY RUN] ✅ Would apply here")
                            applied_count += 1
                            keyword_applied += 1
                            new_urls.append(url)
                            applied_urls.add(url)
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                            continue

                        # Step 3: Click Apply
                        print(f"  🎯 Clicking Apply...")
                        apply_btn.click()
                        time.sleep(2)

                        # Step 4: Fill form
                        print(f"  📝 Filling form...")
                        smart_form_filler.upload_resume(driver, config)
                        smart_form_filler.fill_all_form_fields(driver, config)
                        time.sleep(1)

                        # Step 5: Try submit
                        submitted = False
                        for btn_label in ["Submit", "Apply", "Confirm", "Send"]:
                            try:
                                submit = driver.find_element(
                                    By.XPATH, f"//button[contains(.,'{btn_label}')]")
                                if submit.is_displayed() and submit.is_enabled():
                                    submit.click()
                                    time.sleep(2)
                                    submitted = True
                                    break
                            except:
                                continue

                        if not submitted:
                            result = smart_form_filler.walk_multi_step_form(driver, config, max_steps=6)
                            submitted = result == "submitted"

                        if submitted:
                            print(f"  ✅ Applied successfully!")
                            applied_count += 1
                            keyword_applied += 1
                            new_urls.append(url)
                            applied_urls.add(url)
                        else:
                            print(f"  ⚠️  Could not auto-submit — skipping")

                        # Step 6: Close tab
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except Exception:
                            pass

                    except TimeoutException:
                        print(f"  ⏭️  No apply button found — skipping")
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except Exception:
                            pass

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    ensure_single_tab(driver)

                time.sleep(random.uniform(3, 8))

        print(f"\n[Naukri] ✅ '{keyword}': Applied to {keyword_applied} jobs")

    print(f"\n[Naukri] 📊 Total applied: {applied_count} | New this session: {len(new_urls)}")
    return applied_count, new_urls
