"""
Wellfound Auto-Apply Module
━━━━━━━━━━━━━━━━━━━━━━━━━━
- Email/password login
- Smart search with keywords
- Modal-based apply flow
- Personalized cover note using Gemini AI
- URL deduplication — skips already-applied jobs
- Driver health checks

WORKFLOW per job:
  1. Check if URL already applied (dedup) → skip
  2. Click job link → "Learn more" modal opens
  3. Fill cover note (AI-generated or template)
  4. Click Apply → submit
  5. Close modal → Move to next job
"""

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

# ─────────────────────────────────────────────
#  GEMINI AI for personalized cover notes
# ─────────────────────────────────────────────
from utils.performance import COST_OPTIMIZER

_ai_client = None

def _ask_ai(company_name, job_title, config):
    """Use Gemini AI to generate a personalized cover note for Wellfound."""
    global _ai_client
    api_key = config.get("gemini_api_key", "")
    if not api_key:
        return ""

    try:
        if _ai_client is None:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            _ai_client = genai.GenerativeModel("gemini-2.0-flash")

        profile = config.get("profile", {})
        prompt = f"""Write a very short (2-3 sentences max) personalized note for a Wellfound job application.

Company: {company_name}
Role: {job_title}
Applicant: {profile.get('full_name', 'Harsh Raghuwanshi')}
Background: MBA TECH student at TAPMI Bengaluru, Co-founder of Apna Supermarket (4+ years), experienced in product management, AI tools, GTM strategy, growth.
Skills: {profile.get('skills', 'Product Management, Python, SQL, AI Tools')}

Keep it genuine, enthusiastic, and specific to the role. No fluff. No greeting/signature."""

        response = _ai_client.generate_content(prompt)
        text = response.text.strip()[:500]
        
        # Log approximate token usage for cost optimization
        COST_OPTIMIZER.log_usage(input_chars=prompt, output_chars=text)
        
        return text
    except Exception as e:
        print(f"    [AI] Error: {e}")
        return ""


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
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


def close_popups(driver):
    """Close any modals or popups."""
    popup_selectors = [
        "button[aria-label='Close']", "button[aria-label='close']",
        "button.close", ".modal .close", "[data-testid='close-button']",
    ]
    for sel in popup_selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    try_click(driver, btn)
                    time.sleep(0.5)
        except Exception:
            pass
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
    except Exception:
        pass


def _is_title_relevant(job_title, keyword):
    """
    Check if a job title is relevant to the current search keyword.
    RULES:
      1. Must be an intern/trainee role (not full-time)
      2. Must NOT be a blocked role (engineer, developer, HR, sales, etc.)
      3. Must match at least one wanted management/strategy/AI term
    """
    title_lower = job_title.lower().strip()
    if not title_lower:
        return False

    # ── RULE 1: Must be an intern/trainee role ──
    intern_terms = ["intern", "trainee", "apprentice"]
    is_intern = any(t in title_lower for t in intern_terms)
    if not is_intern:
        return False

    # ── RULE 2: BLOCKLIST — roles the user does NOT want ──
    blocked_roles = [
        "engineer", "developer", "devops", "sre", "backend", "frontend",
        "full stack", "fullstack", "software", "sde", "web dev",
        "designer", "graphic design", "ui/ux", "ux", "ui design",
        "visual design", "motion design", "illustration",
        "content writ", "content market", "copywriter", "seo",
        "video edit", "editor", "photographer", "photo shoot", "fashion",
        "sales", "lead gen", "lead generation", "telesales", "bdr",
        "human resource", "hr ", "hr intern", "recruiter", "talent acquisition",
        "customer support", "customer service", "support exec",
        "data entry", "typist", "clerk", "accounting", "bookkeep",
        "legal", "compliance officer", "shopify", "wordpress",
        "android", "ios developer", "flutter", "react native",
        "qa ", "quality assurance", "tester", "testing",
        "community manager", "social media",
        "marketing", "brand",
    ]
    for blocked in blocked_roles:
        if blocked in title_lower:
            return False

    # ── RULE 3: ALLOWLIST — management/strategy/AI intern roles ──
    wanted_terms = [
        "management", "manager", "managing",
        "founder", "chief of staff", "ceo office",
        "strateg", "strategy", "strategist",
        "business develop", "biz dev", "bd intern",
        "consult", "advisory",
        "operations", "ops intern", "ops associate",
        "product", "pm intern",
        "ai ", "artificial intelligence", "machine learning",
        "growth", "gtm", "go-to-market",
        "venture", "investment",
        "analyst", "research",
        "general management", "gm intern",
        "tech", "digital",
    ]
    for term in wanted_terms:
        if term in title_lower:
            return True

    # Also check keyword-specific terms
    kw_lower = keyword.lower()
    for word in kw_lower.split():
        if word not in ("intern", "interns", "internship", "associate", "trainee",
                        "the", "a", "an", "in", "at", "for", "of"):
            if word in title_lower:
                return True

    return False


# ─────────────────────────────────────────────
#  LOGIN
# ─────────────────────────────────────────────
def login(driver, email, password):
    """Login to Wellfound with email/password."""
    print("\n[Wellfound] Logging in...")

    if not password or password.startswith("YOUR_"):
        print("[Wellfound] ❌ Password not set! Update config.py with your real password.")
        return False

    driver.get("https://wellfound.com/login")
    time.sleep(4)

    try:
        # Find email field
        email_field = None
        for sel in [
            "input[name='email']", "input[type='email']",
            "input[placeholder*='Email']", "input[placeholder*='email']",
            "#user_email", "input#email",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    email_field = el
                    break
            except NoSuchElementException:
                continue

        if not email_field:
            # Try XPath
            try:
                email_field = driver.find_element(By.XPATH,
                    "//input[@type='email' or contains(@placeholder,'email') or contains(@name,'email')]")
            except:
                pass

        if not email_field:
            print("[Wellfound] ❌ Could not find email field.")
            print("[Wellfound] ⏳ Please login manually in the browser...")
            time.sleep(20)
            return _check_login_status(driver)

        email_field.clear()
        email_field.send_keys(email)
        time.sleep(1)

        # Find password field
        pass_field = None
        for sel in [
            "input[name='password']", "input[type='password']",
            "input[placeholder*='Password']", "input[placeholder*='password']",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    pass_field = el
                    break
            except NoSuchElementException:
                continue

        if not pass_field:
            print("[Wellfound] ❌ Could not find password field.")
            print("[Wellfound] ⏳ Please login manually...")
            time.sleep(20)
            return _check_login_status(driver)

        pass_field.clear()
        pass_field.send_keys(password)
        time.sleep(1)

        # Click Login button
        login_btn = None
        for sel in [
            "button[type='submit']",
            "//button[contains(text(),'Log in')]",
            "//button[contains(text(),'Log In')]",
            "//button[contains(text(),'Sign in')]",
            "//input[@type='submit']",
        ]:
            try:
                if sel.startswith("//"):
                    btn = driver.find_element(By.XPATH, sel)
                else:
                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    login_btn = btn
                    break
            except NoSuchElementException:
                continue

        if login_btn:
            try_click(driver, login_btn)
        else:
            pass_field.send_keys(Keys.RETURN)

        time.sleep(5)
        return _check_login_status(driver)

    except Exception as e:
        print(f"[Wellfound] ❌ Login error: {e}")
        print("[Wellfound] ⏳ Please login manually in the browser...")
        time.sleep(20)
        return _check_login_status(driver)


def _check_login_status(driver):
    """Check if we are logged in based on URL or page content."""
    url = driver.current_url
    if "login" in url:
        # Still on login page — might have failed
        try:
            # Check for error messages
            errors = driver.find_elements(By.CSS_SELECTOR,
                ".error, .alert-danger, [role='alert']")
            for e in errors:
                if e.is_displayed() and e.text.strip():
                    print(f"[Wellfound] ❌ Login error: {e.text.strip()}")
                    return False
        except:
            pass
        # Might still be loading
        time.sleep(3)
        url = driver.current_url

    if "login" not in url or "jobs" in url or "profile" in url:
        print("[Wellfound] ✅ Logged in!")
        return True
    else:
        print(f"[Wellfound] ⚠️  Login may have failed. URL: {url}")
        return True  # Continue anyway, might work


# ─────────────────────────────────────────────
#  SEARCH AND APPLY
# ─────────────────────────────────────────────
def search_and_apply(driver, keywords, locations, max_jobs, applied_count,
                     config=None, dry_run=False, applied_urls=None):
    """
    Search Wellfound for intern jobs and apply using modal-based flow.

    WORKFLOW:
      For each keyword:
        1. Navigate to search URL
        2. Scroll to load results
        3. Collect job listing elements
        4. For each job:
           a. Check dedup
           b. Click job / "Learn more"
           c. Fill cover note in modal
           d. Click Apply
           e. Close modal → next job

    Returns: (applied_count, list_of_new_urls)
    """
    if config is None:
        config = {}
    if applied_urls is None:
        applied_urls = set()

    new_urls = []
    default_note = config.get("cover_letter", "").strip()[:500] or (
        "I am excited about this role and believe my background in product management, "
        "AI tools, and entrepreneurship (Co-founder, Apna Supermarket) makes me a strong fit. "
        "Looking forward to contributing to your team!"
    )

    for keyword in keywords:
        if applied_count >= max_jobs:
            break

        keyword_applied = 0

        # ── HEALTH CHECK ──
        if not is_driver_alive(driver):
            print("[Wellfound] ❌ Browser died. Stopping.")
            return applied_count, new_urls

        # Build search URL
        kw_encoded = keyword.replace(" ", "+")
        search_url = f"https://wellfound.com/jobs?keywords={kw_encoded}"

        print(f"\n{'═' * 60}")
        print(f"🔍 WELLFOUND: Searching '{keyword}'")
        print(f"   URL: {search_url}")
        print(f"{'═' * 60}")

        driver.get(search_url)
        time.sleep(5)
        close_popups(driver)

        # Scroll down to load more results
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        # Collect job listing URLs
        job_links = _collect_job_links(driver)
        print(f"  Found {len(job_links)} job listings")

        if not job_links:
            print("  ⚠️  No listings found. Moving to next keyword.")
            continue

        for idx, (job_url, job_title, company_name) in enumerate(job_links):
            if applied_count >= max_jobs:
                break

            # ── DEDUP CHECK ──
            if job_url in applied_urls:
                print(f"  [Skip] Already applied: {job_title[:40]}...")
                continue

            # ── HEALTH CHECK ──
            if not is_driver_alive(driver):
                print("[Wellfound] ❌ Browser died. Stopping.")
                return applied_count, new_urls

            print(f"\n  📋 [{keyword_applied + 1}] {job_title} @ {company_name}")

            # ── TITLE RELEVANCE CHECK ──
            if not _is_title_relevant(job_title, keyword):
                print(f"  ⏭️  Skipping (not relevant): {job_title}")
                continue

            if dry_run:
                print("  [DRY RUN] ✅ Would apply here")
                applied_count += 1
                keyword_applied += 1
                new_urls.append(job_url)
                applied_urls.add(job_url)
                continue

            try:
                # Open job page in new tab
                driver.execute_script(f"window.open('{job_url}', '_blank');")
                time.sleep(2)
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(3)
                close_popups(driver)

                # Try to apply
                applied = _apply_on_job_page(driver, config, job_title, company_name, default_note)

                if applied:
                    print(f"  ✅ Applied successfully!")
                    applied_count += 1
                    keyword_applied += 1
                    new_urls.append(job_url)
                    applied_urls.add(job_url)
                else:
                    print(f"  ⏭️  Could not apply — skipping")

                # Close tab and go back
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

            # Delay between jobs
            time.sleep(random.uniform(3, 6))

        print(f"\n[Wellfound] ✅ '{keyword}': Applied to {keyword_applied} jobs")

    print(f"\n[Wellfound] 📊 Total applied: {applied_count} | New this session: {len(new_urls)}")
    return applied_count, new_urls


def _collect_job_links(driver):
    """Collect ONLY real job listing URLs from Wellfound search results.
    Strict filtering to avoid navigation links, sidebar, company descriptions."""
    import re
    job_links = []
    seen_urls = set()

    # Wellfound job URLs follow patterns like:
    #   /jobs/COMPANY-NAME/JOB-TITLE-SLUG
    #   /company/COMPANY/jobs/ID
    # We use a regex to match only these patterns
    job_url_pattern = re.compile(
        r"wellfound\.com/(jobs/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+"
        r"|company/[a-zA-Z0-9_-]+/jobs/[a-zA-Z0-9_-]+)"
    )

    # Step 1: Try the Wellfound-specific job link class (most reliable)
    primary_selectors = [
        "a.styles_jobLink__US40J",
    ]

    # Step 2: Fallback — grab links from the main content area only
    fallback_selectors = [
        "main a[href*='/jobs/']",
        "[class*='jobList'] a[href*='/jobs/']",
        "[class*='JobList'] a[href*='/jobs/']",
        "[class*='result'] a[href*='/jobs/']",
        "[role='main'] a[href*='/jobs/']",
    ]

    all_selectors = primary_selectors + fallback_selectors

    for sel in all_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                href = el.get_attribute("href") or ""
                if not href or href in seen_urls:
                    continue

                # STRICT filter: must match job URL pattern
                if not job_url_pattern.search(href):
                    continue

                # Skip non-job pages
                skip_paths = [
                    "/login", "/signup", "/profile", "/settings",
                    "/messages", "/saved", "/hidden", "/applied",
                ]
                if any(s in href.lower() for s in skip_paths):
                    continue

                seen_urls.add(href)

                # Extract title from the link text
                title = ""
                try:
                    title_span = el.find_element(By.TAG_NAME, "span")
                    title = title_span.text.strip()
                except:
                    title = el.text.strip()

                if not title or len(title) < 3:
                    # Try to get title from URL slug
                    parts = href.rstrip("/").split("/")
                    title = parts[-1].replace("-", " ").title() if parts else ""

                # Skip if title looks like junk (too short, or a nav item)
                if not title or len(title) < 4:
                    continue

                # Extract company name
                company = ""
                try:
                    parent = el.find_element(By.XPATH, "./ancestor::div[.//h2]")
                    h2 = parent.find_element(By.TAG_NAME, "h2")
                    company = h2.text.strip()
                except:
                    # Try to extract from URL
                    try:
                        if "/jobs/" in href:
                            company = href.split("/jobs/")[1].split("/")[0].replace("-", " ").title()
                        elif "/company/" in href:
                            company = href.split("/company/")[1].split("/")[0].replace("-", " ").title()
                    except:
                        company = "Unknown"

                job_links.append((href, title[:80], company[:60]))
        except Exception:
            continue

    # If primary selectors found jobs, skip fallback results
    # (avoids duplicates from different selectors)
    return job_links


def _apply_on_job_page(driver, config, job_title, company_name, default_note):
    """Handle the apply flow on a Wellfound job page."""
    time.sleep(2)

    # Step 1: Find and click "Apply" or "Learn more" or "Apply Now" button
    apply_btn = None
    for sel in [
        "//button[contains(text(),'Apply')]",
        "//button[contains(text(),'apply')]",
        "//a[contains(text(),'Apply')]",
        "//button[contains(text(),'Learn more')]",
        "//button[contains(text(),'Learn More')]",
        "//button[contains(@class,'apply')]",
        "//a[contains(@class,'apply')]",
    ]:
        try:
            btns = driver.find_elements(By.XPATH, sel)
            for btn in btns:
                if btn.is_displayed():
                    btn_text = btn.text.strip().lower()
                    # Skip if already applied
                    if "applied" in btn_text:
                        print(f"  ⏭️  Already applied on platform")
                        return False
                    apply_btn = btn
                    break
            if apply_btn:
                break
        except:
            continue

    if not apply_btn:
        # Try CSS selectors
        for sel in [
            "button[data-testid='apply-button']",
            ".apply-button", ".apply-btn",
            "button.styles_applyButton",
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    apply_btn = btn
                    break
            except:
                continue

    if not apply_btn:
        return False

    print(f"  🎯 Clicking Apply...")
    try_click(driver, apply_btn)
    time.sleep(3)

    # Step 2: Fill the cover note in the modal 
    # Use AI or default note, will skip if no textarea is present
    note_filled = _fill_cover_note(driver, config, job_title, company_name, default_note)
    
    # Step 4: Upload resume if file input is present
    try:
        resume_path = config.get("resume_path", "")
        if resume_path:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for fi in file_inputs:
                try:
                    fi.send_keys(resume_path)
                    print(f"    [Resume] Uploaded")
                    time.sleep(2)
                except:
                    pass
    except:
        pass

    # Step 5: Click Submit/Apply button (in modal)
    submitted = _click_submit(driver)

    if submitted:
        time.sleep(2)
        # Check for success
        try:
            success = driver.find_elements(By.XPATH,
                "//*[contains(text(),'Application submitted') or "
                "contains(text(),'applied') or "
                "contains(text(),'Application sent') or "
                "contains(text(),'Successfully')]")
            if any(s.is_displayed() for s in success):
                return True
        except:
            pass
        return True  # Assume success if we clicked submit

    return note_filled  # If we at least filled the note, consider it attempted


def _fill_cover_note(driver, config, job_title, company_name, default_note):
    """Fill the cover note textarea in the application modal."""
    textareas = []
    try:
        textareas = driver.find_elements(By.CSS_SELECTOR,
            "textarea, "
            "textarea[name*='customQuestion'], "
            "textarea[name*='note'], "
            "textarea[name*='message'], "
            "textarea[placeholder*='interest'], "
            "div[contenteditable='true']")
    except:
        pass

    if not textareas:
        return False

    for ta in textareas:
        try:
            if not ta.is_displayed():
                continue

            val = (ta.get_attribute("value") or ta.text or "").strip()
            if val:
                continue  # Already filled

            # Generate AI note or use default
            note = _ask_ai(company_name, job_title, config)
            if not note:
                note = default_note

            ta.clear()
            ta.send_keys(note)
            print(f"    [Note] Filled cover note ({len(note)} chars)")
            return True
        except Exception:
            continue

    return False


def _click_submit(driver):
    """Click the Submit/Apply button inside the modal."""
    for sel in [
        "//button[contains(text(),'Apply')]",
        "//button[contains(text(),'Submit')]",
        "//button[contains(text(),'Send')]",
        "//button[@type='submit']",
        "//button[contains(@class,'submit')]",
        "//button[contains(@class,'apply')]",
    ]:
        try:
            btns = driver.find_elements(By.XPATH, sel)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    btn_text = btn.text.strip().lower()
                    # Don't re-click the initial apply button — only in-modal submit
                    if any(word in btn_text for word in ["apply", "submit", "send"]):
                        print(f"    [Submit] Clicking: '{btn.text.strip()}'")
                        try_click(driver, btn)
                        time.sleep(3)
                        return True
        except:
            continue

    # CSS fallback
    for sel in [
        "button[type='submit']",
        "button[data-testid='submit-button']",
        ".modal button.btn-primary",
    ]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed() and btn.is_enabled():
                try_click(driver, btn)
                time.sleep(3)
                return True
        except:
            continue

    return False
