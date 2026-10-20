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
from submit_gate import safety_gate
from url_utils import normalize_url


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
        if "google.com/signin" in url or "/sorry/" in url:
            return True
        # Interstitial "unusual traffic" / reCAPTCHA page is ALSO a wall.
        page_src = (driver.page_source or "").lower()[:5000]
        if "unusual traffic" in page_src or "recaptcha" in page_src:
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
import job_targeting

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
    
    # Content-based detection (best-effort). agent_vision has no detect_ats_type
    # — calling it raised AttributeError and aborted apply_to_job_url for EVERY
    # non-obvious ATS page (LinkedIn, company sites, etc.) → 0 applications. Use
    # the vision helper only if it actually exists, and never let it throw; the
    # URL checks above already catch the known ATS platforms, so anything else
    # falls through to the generic handler.
    fn = getattr(agent_vision, "detect_ats_type", None)
    if callable(fn):
        try:
            from config import CONFIG
            ats_vision = fn(driver, CONFIG)
            if ats_vision and ats_vision != "generic":
                print(f"    👁️ Vision detected ATS: {ats_vision}")
                return ats_vision
        except Exception:
            pass
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
    if result == "review":
        return "review"
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
    if result == "review":
        return "review"
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
                    if not safety_gate(config, label=f"Web Search: {btn_text}"):
                        return "review"
                    print(f"    🚀 Clicking submit: '{btn_text[:30]}'")
                    try_click(driver, btn)
                    time.sleep(3)

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
    return result


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

        if success == "review":
            print(f"    ⏸️  Left tab open for user review ({ats_type})")
        elif success:
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
    # Gather every distinct keyword across all role agents (order-preserving).
    # We round-robin by KEYWORD, not by role agent: the backend merges all of a
    # user's job titles into ONE role agent, so interleaving by agent did nothing
    # and the query budget was spent entirely on the first keyword — the run
    # "only focused on one role". Per-keyword round-robin guarantees every role
    # gets its best query before any role gets a second.
    keywords: list = []
    for agent in config.get("role_agents", []) or []:
        for kw in agent.get("keywords", []) or []:
            if kw and kw not in keywords:
                keywords.append(kw)
    if not keywords:
        keywords = [k for k in (config.get("keywords") or []) if k]
    if not keywords:
        return []

    # Per-keyword query cap — without this, each keyword fans out into board ×
    # ATS × broad queries (each yielding up to 10 tabs), exploding tab count.
    web_cfg = config.get("web_search", {}) or {}
    try:
        per_kw_cap = int(web_cfg.get("max_queries_per_keyword", 6))
    except (TypeError, ValueError):
        per_kw_cap = 6
    per_kw_cap = max(1, min(per_kw_cap, 20))

    per_kw_queries = []  # [(keyword, [q, ...]), ...]
    for kw in keywords:
        qs = job_finder.build_search_queries([kw], config)
        if qs:
            per_kw_queries.append((kw, qs[:per_kw_cap]))

    # Round-robin by keyword so all roles advance together; dedupe queries.
    interleaved: list = []
    seen: set = set()
    if per_kw_queries:
        max_len = max(len(qs) for _, qs in per_kw_queries)
        for i in range(max_len):
            for kw, qs in per_kw_queries:
                if i < len(qs):
                    q = qs[i]
                    key = " ".join((q or "").lower().split())
                    if key and key not in seen:
                        seen.add(key)
                        interleaved.append((kw, q))
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

    applied_norms = {normalize_url(u) for u in applied_urls}

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
    url_set = {normalize_url(u["url"]) for u in all_job_urls}  # local dedup set (O(1) lookups)

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

            results = job_finder.extract_google_links(driver, [u["url"] for u in all_job_urls], applied_urls)
            new_items = []
            for url_str in results:
                if not url_str:
                    continue
                norm = normalize_url(url_str)
                if norm in applied_norms or norm in url_set:
                    continue
                url_set.add(norm)
                new_items.append({"url": url_str})

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

            if success == "review":
                print("  ⏸️  Left tab open for user review.")
                new_applied_urls.append(item)
            elif success:
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


# ─────────────────────────────────────────────
#  PIPELINE (ADR-001): discover → target → fill with ContextFill → close
# ─────────────────────────────────────────────

_CONFIRM_WORDS = ("thank you", "application submitted", "application received",
                  "successfully submitted", "we have received", "applied successfully")


def _google_urls(driver, config, seen_norms, limit, applied_urls=()):
    """Secondary discovery. The first CAPTCHA / sign-in wall ends Google for this run."""
    web_cfg = config.get("web_search") or {}
    out = []
    for i, (_, query) in enumerate(_interleave_role_queries(config)[: int(web_cfg.get("max_queries", 30))]):
        if should_stop() or len(out) >= limit:
            break
        try:
            driver.get(f"https://www.google.com/search?q={quote_plus(query)}&num=10")
            time.sleep(random.uniform(2, 3))
            if _is_google_login_page(driver):
                print("  [Web Search] 🚧 Google CAPTCHA — skipping Google for this run (board APIs still used).")
                break
            for u in job_finder.extract_google_links(driver, [], []):
                n = normalize_url(u)
                if n not in seen_norms and u not in applied_urls:
                    seen_norms.add(n)
                    out.append({"url": u, "title": "", "location": "", "jd": ""})
        except Exception as e:
            print(f"  ⚠️  Google query error: {type(e).__name__}: {str(e)[:100]}")
    return out[:limit]


def _caps_ok(config):
    try:
        from backend.services.apply_decision import rate_ok
    except Exception:
        return True
    return rate_ok(config, "web_search")


def _caps_register(config):
    try:
        from backend.services.apply_decision import rate_register
        rate_register(config, "web_search")
    except Exception:
        pass


def _fit_ok(config, title, jd):
    """LLM fit gate (jd_analyser + fit_scorer). Fail-open when the backend isn't importable."""
    try:
        from backend.services.apply_decision import should_apply
    except Exception:
        return True, ""
    d = should_apply(config, jd_text=jd, title=title or None)
    return d.apply, f"fit {d.score}/100: {d.reasons[-1] if d.reasons else ''}"


def _confirmed(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        return any(w in body for w in _CONFIRM_WORDS)
    except Exception:
        return False


def _close_tabs(driver, handles, home):
    for h in handles:
        try:
            driver.switch_to.window(h)
            driver.close()
        except Exception:
            pass
    try:
        driver.switch_to.window(home if home in driver.window_handles else driver.window_handles[0])
    except Exception:
        pass


def process_job(driver, job, config, ctx, cf=None, home=None):
    """One job, end to end, in its own tab. Returns 'applied' | 'review' | 'skipped' | 'failed'.

    The tab is closed afterwards unless the user has to act on it ('review').
    """
    url = job["url"]
    before = set(driver.window_handles)
    tab_id = None
    if cf:
        _, tab_id = cf.open(url)
    else:
        driver.execute_script("window.open(arguments[0], '_blank');", url)
        time.sleep(random.uniform(2, 3))
    opened = [h for h in driver.window_handles if h not in before]
    if opened:
        driver.switch_to.window(opened[0])
    result = "failed"
    try:
        title = job.get("title") or driver.title or ""
        if not job.get("title"):  # Google result — rules run now that we know the title
            ok, why = job_targeting.check(title, job.get("location"), ctx)
            if not ok:
                print(f"    ⏭ Skipping '{title[:50]}': {why}")
                result = "skipped"
                return result
        jd = job.get("jd") or smart_form_filler._capture_jd_text(driver, {}) or ""
        job["title"], job["jd"] = title, jd  # report_job needs them after this returns
        ok, why = _fit_ok(config, title, jd)
        if not ok:
            print(f"    ⏭ Skipping '{title[:50]}' ({why})")
            result = "skipped"
            return result
        config["_current_jd"], config["_current_title"] = jd, title
        print(f"    🎯 {title[:60]} @ {job.get('company') or urlparse(url).netloc}")

        n = len(driver.window_handles)
        detect_and_click_apply(driver)
        if len(driver.window_handles) > n:  # Apply opened the form in a new tab
            new = driver.window_handles[-1]
            opened.append(new)
            driver.switch_to.window(new)
            time.sleep(2)
            if cf:
                tab_id = cf.active_tab_id(new)

        asks = []
        if cf and tab_id:
            r = cf.fill(tab_id)
            if r["error"]:
                print(f"    ⚠️  ContextFill: {r['error'][:120]} — using built-in filler")
            else:
                asks = r["asks"]
                print(f"    📝 ContextFill filled {r['filled']} field(s), {len(asks)} question(s) for you")
            driver.switch_to.window(opened[-1])
        if not (cf and tab_id) or (cf and r["error"]):
            smart_form_filler.fill_all_form_fields(driver, config)
            google_form_filler.fill_web_form(driver, config)
        if asks:
            config["_unanswered"] = [a.get("question") or a.get("label") or str(a) if isinstance(a, dict) else str(a)
                                     for a in asks]
            print("    ⏸️  Needs your answers — tab left open (see ContextFill badge).")
            result = "review"
            return result

        # ponytail: single-page submit (Greenhouse/Lever); multi-step ATS (Workday) ends in 'review'.
        sub = _submit_application(driver, config)
        if sub == "review":
            result = "review"
        elif sub:
            time.sleep(2)
            result = "applied" if _confirmed(driver) else "review"
            if result == "review":
                print("    ⏸️  Submitted but no confirmation seen — tab left open to check.")
        return result
    except Exception as e:
        print(f"    ❌ apply-error [web_search {url[:100]}]: {type(e).__name__}: {str(e)[:160]}")
        return result
    finally:
        config.pop("_current_jd", None)
        config.pop("_current_title", None)
        if result != "review":
            _close_tabs(driver, opened, home)
        else:
            try:
                driver.switch_to.window(home)
            except Exception:
                pass


def run_pipeline(driver, config, applied_urls=None, cf=None):
    """Phase 6 entry point. Returns (applied_count, processed_urls)."""
    web_cfg = config.get("web_search") or {}
    if isinstance(web_cfg, dict) and web_cfg.get("enabled") is False:
        print("[Web Search] ⏭️  Disabled in config")
        return 0, []
    limit = max(1, min(int(web_cfg.get("tab_limit", 50) or 50), 200))
    ctx = job_targeting.target_ctx(config)
    if not ctx["keywords"]:
        print("[Web Search] ⚠️  No target roles configured — nothing to search")
        return 0, []
    applied_urls = applied_urls if applied_urls is not None else set()
    seen = set()  # this run; the tracker's SkipSet does its own key normalisation + cooldown
    level = job_targeting.LEVELS[ctx["max_level"]]
    print(f"[Web Search] 🎯 Targeting {', '.join(ctx['keywords'])} — up to {level} level"
          f"{'' if ctx['allow_tech'] else ', non-tech'} — {', '.join(ctx['locations'][:4]) or 'any location'}")

    # 1. Board APIs (fast, CAPTCHA-free, carry JD text) → rule filter before any tab opens.
    t0 = time.time()
    postings = job_finder.fetch_board_jobs(web_cfg.get("target_boards") or [])
    n_boards = len(postings)
    if web_cfg.get("jobspy", True):
        postings += job_finder.fetch_jobspy_jobs(
            ctx["keywords"], ctx["locations"],
            web_cfg.get("jobspy_sites") or ["indeed", "naukri", "linkedin", "google"])
    jobs, skipped = [], {}
    for p in postings:
        n = normalize_url(p["url"])
        if n in seen or p["url"] in applied_urls:
            continue
        seen.add(n)
        ok, why = job_targeting.check(p["title"], p["location"], ctx)
        if ok:
            jobs.append(p)
        else:
            key = why.split(" '")[0]
            skipped[key] = skipped.get(key, 0) + 1
    print(f"[Web Search] 🔌 {n_boards} postings from company boards + {len(postings) - n_boards} "
          f"from JobSpy in {time.time() - t0:.1f}s → "
          f"{len(jobs)} match your level/role/location")
    for why, cnt in sorted(skipped.items(), key=lambda x: -x[1])[:4]:
        print(f"    ⏭ Skipped {cnt}: {why.strip()}")

    jobs = job_finder.fetch_jd(jobs[:limit])

    # 2. Google only tops up when the boards didn't fill the budget.
    home = driver.current_window_handle
    if len(jobs) < limit:
        jobs += _google_urls(driver, config, seen, limit - len(jobs), applied_urls)
    jobs = jobs[:limit]
    print(f"[Web Search] 📋 {len(jobs)} job(s) to process, one tab at a time")

    applied, processed = 0, []
    for i, job in enumerate(jobs, 1):
        if should_stop() or not is_driver_alive(driver):
            print("[Web Search] ⏹  Stopping.")
            break
        if not _caps_ok(config):
            break
        print(f"\n  [{i}/{len(jobs)}] {job['url'][:90]}")
        res = process_job(driver, job, config, ctx, cf=cf, home=home)
        # 'failed' (a crash/timeout) is retried next run; applied, review and
        # skipped go on the cooldown so the same JD isn't re-scored every run.
        if res != "failed":
            processed.append(job["url"])
        if res in ("applied", "review"):
            _caps_register(config)
            try:
                from backend.services.apply_decision import report_job
                report_job(config, "applied" if res == "applied" else "prepared",
                           title=job.get("title", ""), company=job.get("company", ""),
                           url=job["url"], jd_text=job.get("jd"))
            except Exception:
                pass
        if res == "applied":
            applied += 1
            print(f"  ✅ Applied ({applied} so far)")
        if res in ("applied", "review"):
            random_delay(config)
    print(f"\n[Web Search] ✅ DONE — {applied} applied, {len(processed)} processed")
    return applied, processed
