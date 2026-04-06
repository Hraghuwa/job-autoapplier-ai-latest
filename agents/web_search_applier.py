"""
🌐 Web Search Auto-Applier — Search Google for jobs on company career pages
& ATS platforms (Lever, Greenhouse, Workday, etc.), then auto-apply using
the shared smart_form_filler module.

WORKFLOW:
  1. Google Search for job listings matching keywords
  2. Collect career page / ATS URLs
  3. For each URL:
     a. Navigate to the job page
     b. Find and click "Apply" button
     c. Fill all form fields (name, email, phone, etc.)
     d. Upload resume
     e. Submit / walk multi-step form
     f. Close tab, move to next
"""

import time
import random
import re
import traceback
from urllib.parse import urlparse, quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    StaleElementReferenceException, ElementNotInteractableException
)

import smart_form_filler
import google_form_filler
import agent_vision


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

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


def random_delay(config):
    """Random delay between applies to appear human."""
    delay_range = config.get("delay_between_applies_sec", (3, 8))
    time.sleep(random.uniform(*delay_range))


# ─────────────────────────────────────────────
#  GOOGLE SEARCH
# ─────────────────────────────────────────────

# Known ATS / career page URL patterns
ATS_PATTERNS = [
    "lever.co", "greenhouse.io", "workday.com", "myworkdayjobs.com",
    "smartrecruiters.com", "icims.com", "ashbyhq.com", "breezy.hr",
    "recruitee.com", "bamboohr.com", "jobvite.com", "applytojob.com",
    "taleo.net", "successfactors.com", "jazz.co",
]

# Domains to skip (not actual job pages)
SKIP_DOMAINS = [
    "linkedin.com", "indeed.com", "glassdoor.com", "naukri.com",
    "internshala.com", "unstop.com", "youtube.com", "facebook.com",
    "twitter.com", "instagram.com", "quora.com", "reddit.com",
    "wikipedia.org", "google.com",
]


def _build_search_queries(config):
    """
    Build Google search queries from role_agents keywords + target companies.
    Only searches for the specific intern roles defined in config.
    Returns a list of (query_string, source_label) tuples.
    """
    # Pull ALL keywords from role_agents (not generic keywords list)
    role_agents = config.get("role_agents", [])
    keywords = []
    for agent in role_agents:
        for kw in agent.get("keywords", []):
            if kw not in keywords:
                keywords.append(kw)

    # Fallback to config keywords if no role_agents
    if not keywords:
        keywords = config.get("keywords", [])

    locations = config.get("locations", [])
    web_cfg = config.get("web_search", {})
    target_companies = web_cfg.get("target_companies", [])
    ats_domains = web_cfg.get("ats_domains", ATS_PATTERNS[:6])

    queries = []

    # 1. ATS platform searches (config keywords only)
    ats_site_filter = " OR ".join(f"site:{d}" for d in ats_domains[:4])
    for kw in keywords[:10]:
        q = f'{kw} "apply" ({ats_site_filter})'
        queries.append((q, f"ATS: {kw}"))

    # 2. Career page searches (config keywords only)
    for kw in keywords:
        q = f'{kw} apply careers India intern 2025 2026'
        queries.append((q, f"Careers: {kw}"))

    # 3. Target company specific searches
    # Randomize to cover different companies and keywords in each loop cycle
    # Take up to 10 companies and 5 keywords per run to avoid 2000+ searches
    selected_companies = random.sample(target_companies, min(10, len(target_companies)))
    selected_keywords = random.sample(keywords, min(5, len(keywords)))

    for company in selected_companies:
        for kw in selected_keywords:
            q = f'{kw} intitle:careers OR inurl:careers site:{company}.com OR site:{company}.in apply'
            queries.append((q, f"Company: {company} — {kw}"))

    return queries


def google_search_jobs(driver, query, max_results=10):
    """
    Search Google for job listings and return a list of URLs.
    Uses the actual Google search page via Selenium.
    """
    urls = []

    try:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
        driver.get(search_url)
        time.sleep(random.uniform(3, 5))

        # Handle consent/cookie screen if present
        try:
            consent_btns = driver.find_elements(By.XPATH,
                "//button[contains(text(),'Accept') or contains(text(),'I agree') "
                "or contains(text(),'Accept all')]")
            for btn in consent_btns:
                if btn.is_displayed():
                    try_click(driver, btn)
                    time.sleep(1)
                    break
        except Exception:
            pass

        # ── Extract links from Google results ──
        # Strategy: grab ALL <a> links on the page, then filter
        # This is more robust than relying on specific Google CSS classes
        # which change frequently.
        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")

        for link in all_links:
            try:
                href = link.get_attribute("href") or ""
                if not href or len(href) < 15:
                    continue
                if href.startswith("javascript:"):
                    continue

                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                path = parsed.path.lower()
                scheme = parsed.scheme.lower()

                # Must be http/https
                if scheme not in ("http", "https"):
                    continue

                # Skip Google's own links and navigation
                if "google." in domain:
                    continue

                # Skip known non-job aggregator domains
                if any(skip in domain for skip in SKIP_DOMAINS):
                    continue

                # Skip image/video/pdf links
                if any(path.endswith(ext) for ext in [".png", ".jpg", ".gif", ".mp4", ".pdf"]):
                    continue

                # Accept: ATS platforms always
                is_ats = any(ats in domain for ats in ATS_PATTERNS)

                # Accept: URLs with career/job-related paths
                is_career = any(w in domain + path for w in [
                    "career", "jobs", "apply", "hiring", "openings",
                    "positions", "opportunities", "recruit", "talent",
                    "vacancy", "vacancies", "work-with-us", "join-us",
                ])

                # Accept: link text mentions jobs
                is_job_text = False
                if not is_ats and not is_career:
                    try:
                        link_text = link.text.strip().lower()
                        if len(link_text) > 5 and any(w in link_text for w in [
                            "apply", "career", "hiring", "job", "intern",
                            "opening", "position", "opportunity",
                        ]):
                            is_job_text = True
                    except Exception:
                        pass

                if is_ats or is_career or is_job_text:
                    # Normalize URL (remove fragments/tracking params)
                    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if parsed.query:
                        clean += f"?{parsed.query}"
                    if clean not in urls:
                        urls.append(clean)

            except Exception:
                continue

    except Exception as e:
        print(f"    ⚠️  Google search error: {e}")

    return urls[:max_results]


# ─────────────────────────────────────────────
#  CAREER PAGE DETECTION & APPLY
# ─────────────────────────────────────────────

def detect_and_click_apply(driver):
    """
    Detect and click the 'Apply' / 'Apply Now' button on a career page.
    Returns True if an apply button was clicked.
    """
    # Common apply button selectors in order of priority
    apply_xpaths = [
        # Exact matches
        "//a[normalize-space()='Apply' or normalize-space()='Apply Now' "
        "or normalize-space()='Apply now' or normalize-space()='APPLY NOW' "
        "or normalize-space()='Apply for this job']",

        "//button[normalize-space()='Apply' or normalize-space()='Apply Now' "
        "or normalize-space()='Apply now' or normalize-space()='APPLY NOW' "
        "or normalize-space()='Apply for this job']",

        # Contains
        "//a[contains(normalize-space(),'Apply')]",
        "//button[contains(normalize-space(),'Apply')]",

        # Input submit
        "//input[@type='submit' and (contains(@value,'Apply') or contains(@value,'APPLY'))]",

        # Lever specific
        "//a[contains(@class,'postings-btn') and contains(text(),'Apply')]",

        # Greenhouse specific
        "//a[@id='apply_button']",

        # Generic career page
        "//a[contains(@href,'apply')]",
        "//a[contains(@class,'apply')]",
        "//button[contains(@class,'apply')]",
    ]

    for xpath in apply_xpaths:
        try:
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        print(f"    🔘 Found apply button: '{btn.text.strip()[:40]}'")
                        try_click(driver, btn)
                        time.sleep(3)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # Vision fallback: ask Gemini to find the apply button
    from config import CONFIG
    vision_result = agent_vision.find_apply_button(driver, CONFIG)
    if vision_result:
        print(f"    👁️ Vision: {vision_result[:60]}")

    return False


def detect_ats_type(url):
    """Detect the ATS platform from the URL."""
    domain = urlparse(url).netloc.lower()
    if "lever.co" in domain:
        return "lever"
    elif "greenhouse.io" in domain:
        return "greenhouse"
    elif "workday" in domain or "myworkdayjobs" in domain:
        return "workday"
    elif "smartrecruiters" in domain:
        return "smartrecruiters"
    elif "ashbyhq" in domain:
        return "ashby"
    elif "icims" in domain:
        return "icims"
    return "generic"


def handle_lever_apply(driver, config):
    """
    Handle Lever ATS application flow.
    Lever typically has: Job page → Apply → Form (single page).
    """
    print("    [Lever] Detected Lever ATS")

    # Click Apply button
    if not detect_and_click_apply(driver):
        # On Lever, the apply form might be on the same page
        # Try scrolling down to find it
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1)
        if not detect_and_click_apply(driver):
            print("    [Lever] Could not find Apply button")
            return False

    time.sleep(2)

    # Fill the Lever form
    smart_form_filler.fill_all_form_fields(driver, config)
    time.sleep(1)
    
    # Run generic web filler as a fallback for standard inputs
    google_form_filler.fill_web_form(driver, config)
    time.sleep(1)

    # Lever has a single submit button
    return _submit_application(driver, config)


def handle_greenhouse_apply(driver, config):
    """
    Handle Greenhouse ATS application flow.
    Greenhouse: Job page → Apply → Multi-section form.
    """
    print("    [Greenhouse] Detected Greenhouse ATS")

    # Click Apply button
    if not detect_and_click_apply(driver):
        print("    [Greenhouse] Could not find Apply button")
        return False

    time.sleep(3)

    # Fill all fields
    smart_form_filler.fill_all_form_fields(driver, config)
    time.sleep(1)
    
    # Run generic web filler as a fallback
    google_form_filler.fill_web_form(driver, config)
    time.sleep(1)

    # Submit
    return _submit_application(driver, config)


def handle_workday_apply(driver, config):
    """
    Handle Workday ATS application flow.
    Workday typically has multi-step forms.
    """
    print("    [Workday] Detected Workday ATS")

    # Click Apply button
    if not detect_and_click_apply(driver):
        print("    [Workday] Could not find Apply button")
        return False

    time.sleep(3)

    # Workday forms are often multi-step
    result = smart_form_filler.walk_multi_step_form(driver, config, max_steps=8)
    return result == "submitted"


def handle_generic_apply(driver, config):
    """
    Handle generic career page application.
    Try to find and click Apply, then fill whatever form appears.
    """
    print("    [Generic] Attempting generic career page apply")

    # First try to click an Apply button
    clicked_apply = detect_and_click_apply(driver)

    if clicked_apply:
        time.sleep(3)

    # Unconditionally fill all form fields
    smart_form_filler.fill_all_form_fields(driver, config)
    time.sleep(1)
    
    # Generic web fallback is perfect here
    google_form_filler.fill_web_form(driver, config)
    time.sleep(1)

    # Try multi-step form walk
    result = smart_form_filler.walk_multi_step_form(driver, config, max_steps=6)
    if result == "submitted":
        return True

    if not clicked_apply:
        # No apply button and no form — might be a listing page
        # Look for individual job links to check
        print("    [Generic] No form found, looking for job links...")

        job_links = driver.find_elements(By.XPATH,
            "//a[contains(@href,'apply') or contains(@href,'job') "
            "or contains(@href,'position') or contains(@href,'opening')]")

        for link in job_links[:3]:
            try:
                href = link.get_attribute("href")
                text = link.text.strip()
                if text and any(w in text.lower() for w in ["apply", "view", "details"]):
                    print(f"    [Generic] Trying job link: {text[:40]}")
                    link.click()
                    time.sleep(3)
                    if detect_and_click_apply(driver):
                        time.sleep(3)
                        smart_form_filler.fill_all_form_fields(driver, config)
                        return _submit_application(driver, config)
                    driver.back()
                    time.sleep(2)
            except Exception:
                continue

    print("    [Generic] Could not complete application flow")
    return False


def _submit_application(driver, config):
    """Try to submit the application form."""
    # Look for submit button
    submit_xpaths = [
        "//button[contains(normalize-space(),'Submit')]",
        "//button[contains(normalize-space(),'Apply')]",
        "//button[contains(normalize-space(),'Send')]",
        "//input[@type='submit']",
        "//button[@type='submit']",
        "//a[contains(normalize-space(),'Submit')]",
    ]

    for xpath in submit_xpaths:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    btn_text = btn.text.strip() or btn.get_attribute("value") or "Submit"
                    print(f"    ✅ Clicking submit: '{btn_text[:30]}'")
                    try_click(driver, btn)
                    time.sleep(1)

                    # Verify submission
                    try:
                        body = driver.find_element(By.TAG_NAME, "body").text.lower()
                        if any(t in body for t in [
                            "success", "submitted", "thank you", "applied",
                            "received", "congratulations", "confirmation"
                        ]):
                            print("    ✅ Application submitted successfully!")
                            return True
                    except Exception:
                        pass
                    # Assume submitted if button was clicked
                    return True
        except Exception:
            continue

    # If no submit button found, try the multi-step form walker
    result = smart_form_filler.walk_multi_step_form(driver, config, max_steps=5)
    return result == "submitted"


# ─────────────────────────────────────────────
#  APPLY TO A SINGLE JOB URL
# ─────────────────────────────────────────────

def apply_to_job_url(driver, url, config, dry_run=False):
    """
    Navigate to a job URL, detect ATS type, fill form, and apply.
    Returns True if application was submitted (or attempted).
    """
    # Check stop event at entry — avoids starting a 30s fill if already stopped
    _stop = config.get("_stop_event")
    if _stop and _stop.is_set():
        return False

    print(f"\n    🌐 Opening: {url[:80]}...")

    try:
        # Open in a new tab instead of navigating the current one
        driver.execute_script(f"window.open('{url}', '_blank');")
        # Switch to the new tab which is the last one in the list
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(random.uniform(3, 5))

        # Check if page loaded
        if "error" in driver.title.lower() or "404" in driver.title:
            print("    ⚠️  Page not found, skipping")
            return False

        # Vision: check if this is a relevant job
        if not agent_vision.is_relevant_job(driver, config):
            print("    ⚠️  Vision says: not a relevant job, skipping")
            return False

        if dry_run:
            print("    🔍 [DRY RUN] Would apply here")
            # Still detect form for logging
            ats = detect_ats_type(url)
            print(f"    📋 ATS type: {ats}")
            detect_and_click_apply(driver)
            return False

        # Detect ATS and use appropriate handler
        ats_type = detect_ats_type(url)

        handlers = {
            "lever": handle_lever_apply,
            "greenhouse": handle_greenhouse_apply,
            "workday": handle_workday_apply,
        }

        handler = handlers.get(ats_type, handle_generic_apply)
        # Check stop again right before the potentially long form-fill step
        if _stop and _stop.is_set():
            return False
        success = handler(driver, config)

        if success:
            print(f"    ✅ Applied via {ats_type}")
        else:
            print(f"    ⚠️  Could not auto-apply ({ats_type}) — tab left open")

        return success

    except Exception as e:
        print(f"    ❌ Error applying: {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────
#  MAIN: SEARCH & APPLY
# ─────────────────────────────────────────────

def search_and_apply(driver, config, applied_urls=None):
    """
    Main entry point — search Google for jobs and auto-apply.
    Returns: (applied_count, list_of_new_urls)
    """
    if applied_urls is None:
        applied_urls = set()
    else:
        applied_urls = set(applied_urls)

    web_cfg = config.get("web_search", {})
    if not web_cfg.get("enabled", True):
        print("[Web Search] ⏭️  Disabled in config")
        return 0, []

    max_results = web_cfg.get("max_results_per_query", 10)
    dry_run = config.get("dry_run", False)
    delay_range = config.get("delay_between_applies_sec", (3, 8))

    queries = _build_search_queries(config)
    all_job_urls = []
    new_applied_urls = []
    applied_count = 0
    _stop = config.get("_stop_event")

    print(f"\n[Web Search] 🔍 Running {len(queries)} search queries...")

    # Phase 1: Collect all job URLs from Google
    for i, (query, label) in enumerate(queries):
        if _stop and _stop.is_set():
            print("[Web Search] 🛑 Stop requested — exiting search.")
            break
        if not is_driver_alive(driver):
            print("[Web Search] ❌ Browser died, stopping")
            break

        print(f"\n  [{i+1}/{len(queries)}] 🔎 {label}")
        print(f"  Query: {query[:80]}...")

        try:
            urls = google_search_jobs(driver, query, max_results)
        except Exception as e:
            print(f"  ❌ Google search failed for '{label}': {type(e).__name__}: {e}")
            continue
        new_urls = [u for u in urls if u not in applied_urls and u not in all_job_urls]

        print(f"  📋 Found {len(urls)} results, {len(new_urls)} new")

        all_job_urls.extend(new_urls)

        # Small delay between Google searches to avoid rate limiting
        time.sleep(random.uniform(3, 6))

        # Cap total URLs to avoid extremely long runs
        if len(all_job_urls) >= 50:
            print("  📊 Reached 50 URL cap, stopping search phase")
            break

    print(f"\n[Web Search] 📊 Total unique job URLs collected: {len(all_job_urls)}")

    if not all_job_urls:
        print("[Web Search] ℹ️  No new job URLs found")
        return 0, []

    # Phase 2: Apply to each job URL
    print(f"\n[Web Search] 🎯 Applying to {len(all_job_urls)} jobs...")

    for i, url in enumerate(all_job_urls):
        if _stop and _stop.is_set():
            print("[Web Search] 🛑 Stop requested — exiting apply.")
            break
        if not is_driver_alive(driver):
            print("[Web Search] ❌ Browser died, stopping")
            break

        print(f"\n{'─' * 50}")
        print(f"  [{i+1}/{len(all_job_urls)}] Applying: {url[:80]}")

        try:
            success = apply_to_job_url(driver, url, config, dry_run)

            if success:
                applied_count += 1
                new_applied_urls.append(url)
                print(f"  ✅ Total applied: {applied_count}")
            else:
                # Still track the URL to avoid retrying
                new_applied_urls.append(url)

        except Exception as e:
            print(f"  ❌ Error on {url[:80]}: {type(e).__name__}: {e}")
            traceback.print_exc()

        # Check stop after each job — ensures we exit promptly after the current URL
        if _stop and _stop.is_set():
            print("[Web Search] 🛑 Stop requested — exiting after current job.")
            break

        # Ensure we're back to one tab - NO, we want to keep them open for manual review
        # ensure_single_tab(driver)

        # Random delay
        time.sleep(random.uniform(*delay_range))

    print(f"\n[Web Search] ✅ DONE — Applied to {applied_count} jobs")
    print(f"[Web Search] 📊 URLs processed: {len(all_job_urls)}")

    return applied_count, new_applied_urls
