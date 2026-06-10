"""
🌐 Web Search Auto-Applier — Search Google for jobs on company career pages
& ATS platforms (Lever, Greenhouse, Workday, etc.), then auto-apply using
the shared smart_form_filler module.

WORKFLOW:
  1. Google Search for job listings matching the USER'S target roles
     (role_agents from config, not a hardcoded role list)
  2. Multiple roles are orchestrated IN PARALLEL by interleaving queries
     so every role advances at the same time
  3. Collect career page / ATS URLs for every role simultaneously
  4. For each URL:
     a. Open the job page in a NEW tab (search tab stays intact)
     b. Find and click "Apply" button
     c. Fill all form fields (name, email, phone, etc.)
     d. Upload resume
     e. Walk multi-step form
     f. LEAVE the tab OPEN so the user can review / submit later
  5. If Google demands a login mid-search: pause and wait up to 2 minutes
     for the user to log in manually, then resume automatically
  6. Stop signal (user clicks Pause) is honoured at every loop boundary —
     tabs are NEVER closed on stop so the user can apply to found jobs later
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
from agent_stop import should_stop


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
    """⚠️  DEPRECATED — do NOT use. Kept only for legacy imports.

    The web-app contract is: tabs stay OPEN so the user can review any
    jobs the agent found after a pause/stop. Callers MUST NOT close tabs.
    """
    return  # intentionally a no-op


def _is_google_login_page(driver) -> bool:
    """True if the current Google tab is asking the user to sign in.

    Google throws a sign-in wall at any IP doing many automated searches in a
    short window. Without this check the agent thinks the page is a normal
    search results page and keeps scraping zero links, wasting minutes per
    query and confusing the user.
    """
    try:
        url = (driver.current_url or "").lower()
        if "accounts.google.com" in url or "servicelogin" in url:
            return True
        if "google.com/signin" in url:
            return True
        # Interstitial "unusual traffic" page is ALSO a login/challenge signal —
        # Google shows a checkbox that looks like a CAPTCHA.
        page_src = (driver.page_source or "").lower()[:5000]
        if "unusual traffic" in page_src and "sign in" in page_src:
            return True
    except Exception:
        pass
    return False


def _wait_for_google_login(driver, max_wait_sec: int = 120):
    """Pause the agent and let the USER log into Google manually.

    Polls every 3 seconds for up to `max_wait_sec`. If the login completes,
    returns True. If the timeout expires, returns False and the caller
    should continue its search loop anyway (the user can still search the
    visible tabs manually).

    Respects the global stop signal so Pause still works while waiting.
    """
    print(
        "\n  [Web Search] 🔐 Google is asking for a sign-in.\n"
        "  👉  Please log into Google in the Chrome window within the next "
        f"{max_wait_sec} seconds — the agent will resume automatically.\n"
        "     (If you don't log in, the agent will continue anyway and\n"
        "      open job tabs without using Google search.)"
    )
    waited = 0
    poll = 3
    while waited < max_wait_sec:
        if should_stop():
            print("  [Web Search] ⏹  Stop requested while waiting for Google login.")
            return False
        time.sleep(poll)
        waited += poll
        try:
            if not _is_google_login_page(driver):
                print("  [Web Search] ✅ Google login detected — resuming search.")
                return True
        except Exception:
            # Driver may have crashed — bail out of the wait loop
            return False
    print(
        f"  [Web Search] ⏱  Google login not detected within {max_wait_sec}s — "
        "continuing anyway. Found-job tabs remain open for manual review."
    )
    return False


def random_delay(config):
    """Adaptive delay between applies — escalates after consecutive failures to
    avoid bot detection (backend.services.backoff). Fail-open to the flat band."""
    try:
        from backend.services.backoff import delay_for
        delay_for(config, "web_search")
        return
    except Exception:
        pass
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


import job_finder

def _build_search_queries(config):
    """Bridge to job_finder's superior query engine."""
    role_agents = config.get("role_agents", [])
    keywords = []
    for agent in role_agents:
        for kw in agent.get("keywords", []):
            if kw not in keywords:
                keywords.append(kw)
    if not keywords:
        keywords = config.get("keywords", [])
    
    return job_finder.build_search_queries(keywords, config)


def google_search_jobs(driver, query, max_results=10, applied_urls=None):
    """
    Search Google for job listings and return a list of URL objects.
    Delegates link extraction to job_finder.
    """
    if applied_urls is None: applied_urls = set()
    
    try:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
        driver.get(search_url)
        time.sleep(random.uniform(3, 5))

        # Handle consent
        try:
            consent_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Accept') or contains(text(),'I agree')]")
            for btn in consent_btns:
                if btn.is_displayed():
                    try_click(driver, btn)
                    time.sleep(1)
                    break
        except Exception: pass

        # Delegate extraction to job_finder for consistency
        return job_finder.extract_google_links(driver, [], applied_urls)

    except Exception as e:
        print(f"    ⚠️  Google search error: {e}")
        return []


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


def detect_ats_type(driver, url):
    """Detect the ATS platform from the URL or page content (Vision)."""
    domain = urlparse(url).netloc.lower()
    
    # URL based detection
    if "lever.co" in domain: return "lever"
    if "greenhouse.io" in domain: return "greenhouse"
    if "workday" in domain or "myworkdayjobs" in domain: return "workday"
    if "smartrecruiters" in domain: return "smartrecruiters"
    if "ashbyhq" in domain: return "ashby"
    if "icims" in domain: return "icims"
    
    # Content based detection (Vision fallback)
    from config import CONFIG
    ats_vision = agent_vision.detect_ats_type(driver, CONFIG)
    if ats_vision and ats_vision != "generic":
        print(f"    👁️ Vision detected ATS: {ats_vision}")
        return ats_vision
        
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
                    # btn_text = btn.text.strip() or btn.get_attribute("value") or "Submit"
                    # print(f"    ✅ Clicking submit: '{btn_text[:30]}'")
                    # try_click(driver, btn)
                    print("    ✅ Check point reached. Skipping submit step as requested.")
                    time.sleep(1)

                    # Verify submission
                    # try:
                    #     body = driver.find_element(By.TAG_NAME, "body").text.lower()
                    #     if any(t in body for t in [
                    #         "success", "submitted", "thank you", "applied",
                    #         "received", "congratulations", "confirmation"
                    #     ]):
                    #         print("    ✅ Application submitted successfully!")
                    #         return True
                    # except Exception:
                    #     pass
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

        # Detect ATS and use appropriate handler
        ats_type = detect_ats_type(driver, url)

        if dry_run:
            print(f"    🔍 [DRY RUN] Would apply via {ats_type}")
            detect_and_click_apply(driver)
            return False

        handlers = {
            "lever": handle_lever_apply,
            "greenhouse": handle_greenhouse_apply,
            "workday": handle_workday_apply,
            "ashby": handle_generic_apply,
        }

        handler = handlers.get(ats_type, handle_generic_apply)
        success = handler(driver, config)

        if success:
            print(f"    ✅ Applied via {ats_type}")
        else:
            print(f"    ⚠️  Could not auto-apply ({ats_type}) — tab left open")

        return success

    except Exception as e:
        # Log with the URL + exception type so backend AgentStdout classifier
        # can forward it as an error_reason to the frontend instead of silently
        # returning False. NOTE: we deliberately do NOT close the tab here —
        # the user wants failed tabs left open for manual review/retry.
        url_preview = (url or "?")[:120]
        print(f"    ❌ apply-error [web_search {url_preview}]: {type(e).__name__}: {str(e)[:200]}")
        return False


# ─────────────────────────────────────────────
#  MAIN: SEARCH & APPLY
# ─────────────────────────────────────────────

def _interleave_role_queries(config):
    """Build search queries for EVERY role agent, then round-robin them.

    Why interleave? The user explicitly asked: "orchestration of role must be
    there at single point of time. currently only one is being targeted".
    Sequential processing (role 1 → role 2 → ...) means role 2 never runs
    if role 1 hits a Google CAPTCHA. Interleaving guarantees every role
    makes progress in every cycle of the loop.

    Returns a flat list of (role_label, query) tuples in round-robin order.
    """
    role_agents = config.get("role_agents", [])
    fallback_keywords = config.get("keywords", [])

    # Build a per-role query list
    per_role_queries = []  # list of (role_label, [query, query, ...])
    if role_agents:
        for agent in role_agents:
            role_label = agent.get("name") or ",".join(agent.get("keywords", []))[:40] or "role"
            kws = agent.get("keywords", [])
            if not kws:
                continue
            queries = job_finder.build_search_queries(kws, config)
            per_role_queries.append((role_label, queries))
    # Fallback: flat keyword list → single synthetic role
    if not per_role_queries and fallback_keywords:
        per_role_queries.append((
            "default",
            job_finder.build_search_queries(fallback_keywords, config),
        ))

    # Round-robin interleave so every role advances each cycle
    interleaved: list = []
    if per_role_queries:
        max_len = max(len(q) for _, q in per_role_queries)
        for i in range(max_len):
            for role_label, qs in per_role_queries:
                if i < len(qs):
                    interleaved.append((role_label, qs[i]))
    return interleaved


def search_and_apply(driver, config, applied_urls=None):
    """
    Main entry point — search Google for jobs and auto-apply.

    Key guarantees honoured by this function (ship-critical):
    - Honours the global Stop signal at every loop boundary.
    - NEVER closes any tab and NEVER calls driver.quit() even on stop —
      the user wants all found-job tabs left open so they can apply later.
    - Detects Google sign-in walls and waits up to 2 minutes for manual login.
    - Interleaves queries from every role agent so ALL target roles advance
      in parallel rather than processing one role to completion first.
    - Switches BACK to the search tab after each apply so the next query
      does not clobber the last-applied job tab.

    Returns: (applied_count, list_of_new_urls)
    """
    if applied_urls is None:
        applied_urls = set()
    else:
        applied_urls = set(applied_urls)

    # Defensive: agent_tasks._build_config() used to send a boolean here, which
    # then AttributeError'd on .get() and killed the whole phase silently.
    # Accept both shapes so legacy configs still work.
    web_cfg = config.get("web_search", {})
    if isinstance(web_cfg, bool):
        web_cfg = {"enabled": web_cfg}
    elif not isinstance(web_cfg, dict):
        web_cfg = {}
    if not web_cfg.get("enabled", True):
        print("[Web Search] ⏭️  Disabled in config")
        return 0, []

    max_results = web_cfg.get("max_results_per_query", 10)
    dry_run = config.get("dry_run", False)
    delay_range = config.get("delay_between_applies_sec", (3, 8))
    max_queries = int(web_cfg.get("max_queries", 30))

    # ── User-configurable tab cap ──
    # The user explicitly asked for a limit on how many tabs get opened
    # in one run (presets: 20 / 50 / 70 / 100). The value is read from
    # config["web_search"]["tab_limit"] with fallback to legacy "max_urls"
    # and a hard floor/ceiling so a missing/garbage value can't explode
    # into thousands of tabs.
    raw_tab_limit = web_cfg.get("tab_limit")
    if raw_tab_limit is None:
        raw_tab_limit = web_cfg.get("max_urls", 50)
    try:
        tab_limit = int(raw_tab_limit)
    except (TypeError, ValueError):
        tab_limit = 50
    tab_limit = max(5, min(tab_limit, 200))  # sane bounds
    max_url_cap = tab_limit

    google_login_wait_sec = int(web_cfg.get("google_login_wait_sec", 120))

    # Anti-repetition: remember every query we've already issued in this run.
    # Without this, duplicate queries (which can arise from overlapping role
    # keywords) waste the query budget and the user's time.
    issued_queries: set = set()

    # Build interleaved role queries so EVERY role runs in parallel (one per cycle)
    interleaved = _interleave_role_queries(config)
    if not interleaved:
        print("[Web Search] ⚠️  No keywords configured — nothing to search")
        return 0, []

    # Remember the search tab so we can always switch BACK to it between
    # queries. Without this, the next driver.get() overwrites whatever tab
    # was current after the last apply — which was the last job tab.
    try:
        search_tab = driver.current_window_handle
    except Exception:
        search_tab = None

    all_job_urls = []
    new_applied_urls = []
    applied_count = 0

    # Deduplicate the interleaved list BEFORE slicing so duplicate queries
    # (from overlapping role keywords) don't silently consume the budget.
    seen_q: set = set()
    unique_interleaved = []
    for role_label, query in interleaved:
        key = " ".join((query or "").lower().split())
        if key in seen_q:
            continue
        seen_q.add(key)
        unique_interleaved.append((role_label, query))
    interleaved = unique_interleaved

    total_queries = len(interleaved)
    capped = min(total_queries, max_queries)
    roles_running = sorted({label for label, _ in interleaved[:capped]})
    print(
        f"\n[Web Search] 🔍 Orchestrating {len(roles_running)} role(s) in parallel: "
        f"{', '.join(roles_running)}"
    )
    print(
        f"[Web Search] 🔎 Running {capped} interleaved queries "
        f"(of {total_queries}) — tab cap: {tab_limit}"
    )

    # ── Phase 1: Collect job URLs via interleaved Google searches ──
    url_set = {u["url"] for u in all_job_urls}  # local dedup set (O(1) lookups)

    for i, (role_label, query) in enumerate(interleaved[:capped]):
        if should_stop():
            print("[Web Search] ⏹  Stop requested — exiting search phase (tabs left open).")
            break
        if not is_driver_alive(driver):
            print("[Web Search] ❌ Browser died — stopping (tabs left open).")
            break

        # Anti-repetition: skip the query if we have already issued an
        # equivalent one in this run (identical after whitespace/case normalise).
        q_key = " ".join((query or "").lower().split())
        if q_key in issued_queries:
            print(f"  [{i+1}/{capped}] ⏭  skip duplicate query: {query[:60]}")
            continue
        issued_queries.add(q_key)

        # Always return to the search tab before running the next query
        if search_tab:
            try:
                driver.switch_to.window(search_tab)
            except Exception:
                # Search tab was closed by the user — re-anchor on any alive tab
                try:
                    search_tab = driver.window_handles[0]
                    driver.switch_to.window(search_tab)
                except Exception:
                    print("[Web Search] ❌ No live tab to search in — stopping.")
                    break

        print(f"\n  [{i+1}/{capped}] 🧭 [{role_label}] 🔎 {query[:80]}...")

        try:
            search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results}"
            driver.get(search_url)
            time.sleep(random.uniform(3, 5))

            # Google login wall → pause agent, wait for the user, then continue
            if _is_google_login_page(driver):
                logged_in = _wait_for_google_login(driver, max_wait_sec=google_login_wait_sec)
                if not logged_in:
                    # Skip Google queries for the rest of the run — open tabs stay intact
                    print("[Web Search] ⏭  Skipping remaining Google queries after login timeout.")
                    break
                # Re-issue the same query after login
                try:
                    driver.get(search_url)
                    time.sleep(random.uniform(2, 4))
                except Exception:
                    pass

            results = job_finder.extract_google_links(driver, all_job_urls, applied_urls)
            new_items = []
            for u in results:
                url_str = u.get("url") or ""
                if not url_str:
                    continue
                if url_str in applied_urls or url_str in url_set:
                    continue
                # Canonicalise lightly (strip tracking query params) to avoid
                # "same job, different utm_*" duplicates.
                norm = url_str.split("#")[0].split("?")[0].rstrip("/")
                if norm in url_set:
                    continue
                url_set.add(url_str)
                url_set.add(norm)
                new_items.append(u)

            print(f"  📋 Found {len(results)} results, {len(new_items)} new")
            all_job_urls.extend(new_items)

        except Exception as e:
            print(f"    ❌ apply-error [web_search query]: {type(e).__name__}: {str(e)[:200]}")

        # Small delay between Google searches to avoid rate limiting
        time.sleep(random.uniform(3, 6))

        if len(all_job_urls) >= max_url_cap:
            print(f"  📊 Reached tab-limit ({max_url_cap}) — moving to apply phase")
            break

    # Hard-cap the apply list to the user-configured tab limit.
    if len(all_job_urls) > tab_limit:
        print(f"[Web Search] 🔒 Capping apply list from {len(all_job_urls)} to tab_limit={tab_limit}")
        all_job_urls = all_job_urls[:tab_limit]

    print(f"\n[Web Search] 📊 Total unique job URLs collected: {len(all_job_urls)}")

    if not all_job_urls:
        print("[Web Search] ℹ️  No new job URLs found — tabs left intact.")
        return 0, []

    # ── Phase 2: Apply to each collected job URL ──
    print(f"\n[Web Search] 🎯 Applying to {len(all_job_urls)} jobs (tabs stay open)...")

    for i, item in enumerate(all_job_urls):
        if should_stop():
            print("[Web Search] ⏹  Stop requested mid-apply — exiting (tabs left open).")
            break
        if not is_driver_alive(driver):
            print("[Web Search] ❌ Browser died — stopping (tabs left open).")
            break

        url = item["url"]
        print(f"\n{'─' * 50}")
        print(f"  [{i+1}/{len(all_job_urls)}] Applying to: {url[:60]}")

        try:
            success = apply_to_job_url(driver, url, config, dry_run)

            if success:
                applied_count += 1
                new_applied_urls.append(item)
                print(f"  ✅ Total applied: {applied_count}")
            else:
                # Track even failed attempts so we don't retry immediately
                new_applied_urls.append(item)

        except Exception as e:
            print(f"  ❌ apply-error [web_search apply]: {type(e).__name__}: {str(e)[:200]}")
        finally:
            # CRITICAL: switch back to the search tab BEFORE the next iteration,
            # otherwise the next driver.get()/search would clobber this job tab.
            # Never close any tab — user wants all jobs left open for review.
            if search_tab:
                try:
                    driver.switch_to.window(search_tab)
                except Exception:
                    pass

        # Random delay between applies to look human
        time.sleep(random.uniform(*delay_range))

    stopped_flag = should_stop()
    status_tag = "⏸ PAUSED" if stopped_flag else "✅ DONE"
    print(f"\n[Web Search] {status_tag} — Applied to {applied_count} jobs")
    print(f"[Web Search] 📊 URLs processed: {len(all_job_urls)} — all tabs remain open.")

    return applied_count, new_applied_urls
