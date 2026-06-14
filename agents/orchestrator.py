"""
🧠 Multi-Agent Orchestrator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1 — LinkedIn Auto-Apply
      Login → search jobs → Easy Apply modal OR external tab
      Auto-fills every form field + uploads resume

Phase 2 — Web Search + ATS Auto-Apply
      Google → Lever / Greenhouse / Workday / career pages
      Auto-fills + uploads resume on each found job

Phase 3 — Form Fill (all open tabs)
      Scans every open browser tab
      Detects Google Forms / web forms automatically
      Fills all fields + uploads resume

Phase 4 — Wellfound Search + Apply
      Login → search intern keywords
      Fills cover note + applies

Phases run CONCURRENTLY for maximum throughput.
Select specific phases: python orchestrator.py 1 2 3 4
"""

import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import CONFIG
from utils.performance import PERFORMANCE_TRACKER, COST_OPTIMIZER

import linkedin_applier
import internshala_applier
import job_finder
import google_form_filler
import web_search_applier
import wellfound_applier
import other_platforms
from main import load_tracker, save_tracker, get_applied_urls, add_applied_urls


# ─────────────────────────────────────────────
#  SERVER-MODE TEARDOWN (audit N1)
# ─────────────────────────────────────────────
# Layer-A (local CLI) intentionally leaves tabs open for the human to review.
# Layer-B (the SaaS worker) has no human at the browser, so leaving Chrome alive
# leaks one process per run and eventually OOMs the box. The worker sets
# CONFIG["_server_mode"]=True; in that mode we DON'T detach and we DO quit().
def _server_mode() -> bool:
    try:
        if CONFIG.get("_server_mode"):
            return True
    except Exception:
        pass
    return os.environ.get("JOBAGENT_SERVER_MODE") == "1"


def _resolve_chrome_paths():
    """Return (chrome_binary, chromedriver_path) to use, from env when present.

    The worker container sets CHROME_BIN / CHROMEDRIVER_PATH to the distro
    Chromium so Selenium doesn't need a runtime webdriver-manager download.
    Returns (None, None) for local dev → fall back to webdriver-manager.
    Only returns a path if it actually exists on disk.
    """
    chrome_bin = os.environ.get("CHROME_BIN") or ""
    driver_path = os.environ.get("CHROMEDRIVER_PATH") or ""
    chrome_bin = chrome_bin if chrome_bin and os.path.exists(chrome_bin) else None
    driver_path = driver_path if driver_path and os.path.exists(driver_path) else None
    return chrome_bin, driver_path


def _teardown(driver, phase_label: str = "") -> None:
    if driver is None:
        return
    if _server_mode():
        try:
            driver.quit()
            print(f"  [{phase_label}] 🧹 Browser closed (server mode).")
        except Exception:
            pass
    else:
        print(f"  [{phase_label}] 🌐 Browser session preserved — tabs left open for review.")


# ─────────────────────────────────────────────
#  SHARED BROWSER FACTORY
# ─────────────────────────────────────────────
def create_driver(profile_suffix=""):
    """
    Create a Chrome driver with a persistent profile so logins survive
    across phases. profile_suffix allows each phase its own profile dir.
    """
    opts = Options()
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # CRITICAL: detach=True keeps Chrome alive after the Python driver object
    # is garbage collected. Without this, every phase exit (normal OR stop)
    # would close all found-job tabs the user wants to review later.
    opts.add_experimental_option("detach", not _server_mode())
    # Incognito: ensures no cached login session bypasses credential-based login
    opts.add_argument("--incognito")

    # In a container (worker image) use the distro Chromium + driver via env —
    # avoids a runtime webdriver-manager download and Chrome/driver version
    # drift. Falls back to webdriver-manager for local dev.
    chrome_bin, driver_path = _resolve_chrome_paths()
    if chrome_bin:
        opts.binary_location = chrome_bin

    if driver_path:
        binary = driver_path
    else:
        import glob as _glob
        wdm_path = ChromeDriverManager().install()
        driver_dir = os.path.dirname(wdm_path)
        candidates = _glob.glob(os.path.join(driver_dir, "chromedriver*"))
        binary = next((p for p in candidates if os.path.isfile(p) and "NOTICES" not in p), wdm_path)
        try:
            os.chmod(binary, 0o755)
        except OSError:
            pass

    driver = webdriver.Chrome(service=Service(binary), options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    try:
        driver.set_window_position(50, 50)
    except Exception:
        pass
    time.sleep(2)
    return driver


def _autofill_all_tabs(driver, label=""):
    """
    Scan every open tab — detect form type and auto-fill + upload resume.
    Called after any phase that may have opened new tabs.
    """
    try:
        filled, fields = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        print(f"  [{label}] 📝 Auto-filled {fields} fields across {filled} tabs")
        return filled
    except Exception as e:
        print(f"  [{label}] ⚠️  Auto-fill error: {e}")
        return 0


# ─────────────────────────────────────────────
#  PHASE 1: LINKEDIN AUTO-APPLY
# ─────────────────────────────────────────────
def run_linkedin_phase():
    """
    Phase 1: LinkedIn
    - Login once, reuse session across all role agents
    - For each job: Easy Apply modal (auto-fill) OR external tab (auto-fill)
    - Resume uploaded in both flows
    """
    phase_name = "Phase 1: LinkedIn Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    try:
        driver = create_driver("_linkedin")

        linkedin_email = CONFIG.get("linkedin", {}).get("email", "")
        linkedin_pwd   = CONFIG.get("linkedin", {}).get("password", "")

        if not linkedin_email or not linkedin_pwd or linkedin_pwd.startswith("YOUR_"):
            print("  [Phase 1] ❌ LinkedIn credentials not set.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="No credentials")
            return 0

        print("  [Phase 1] 🔐 Logging into LinkedIn...")
        login_ok = linkedin_applier.login(driver, linkedin_email, linkedin_pwd)
        if not login_ok:
            print("  [Phase 1] ❌ Login failed.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="Login failed")
            return 0

        print("  [Phase 1] ✅ Logged in — starting role agents...")

        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)

        for agent in CONFIG.get("role_agents", []):
            if isinstance(agent, str):
                name = agent
                keywords = [agent]
                emoji = "🔹"
            else:
                name = agent.get("name", "Unknown")
                keywords = agent.get("keywords", [])
                emoji = agent.get("emoji", "🔹")

            print(f"  [Phase 1] {emoji} Agent: {name}")
            cfg = dict(CONFIG)
            cfg["keywords"] = keywords
            count = linkedin_applier.run(
                driver, cfg, 0, CONFIG["max_jobs_per_day"],
                applied_urls=applied_urls
            )
            applied += count

        # Final pass: fill any external tabs that were left open
        _autofill_all_tabs(driver, "Phase 1")

        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 1] ✅ Done — {applied} LinkedIn applications")

    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        # Tabs ALWAYS stay open (both on stop AND on normal completion) so the
        # user can review/apply to jobs manually. detach=True + no driver.quit()
        # is the contract enforced at every phase boundary.
        _teardown(driver, "Phase 1")

    return applied


# ─────────────────────────────────────────────
#  PHASE 2: INTERNSHALA AUTO-APPLY
# ─────────────────────────────────────────────
def run_internshala_phase():
    """Phase 2: Internshala search + apply."""
    phase_name = "Phase 2: Internshala Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    creds = CONFIG.get("internshala", {}) or {}
    email = creds.get("email", "")
    password = creds.get("password", "")
    if not email or not password or password.startswith("YOUR_"):
        print("  [Phase 2] ❌ Internshala credentials not set — skipping.")
        PERFORMANCE_TRACKER.end_phase(phase_name, error="No credentials")
        return 0

    try:
        driver = create_driver("_internshala")
        print("  [Phase 2] 🔐 Logging into Internshala...")
        if not internshala_applier.login(driver, email, password):
            print("  [Phase 2] ❌ Internshala login failed.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="Login failed")
            return 0

        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)
        applied, new_urls = internshala_applier.search_and_apply(
            driver,
            keywords=CONFIG["keywords"],
            locations=CONFIG["locations"],
            max_jobs=CONFIG["max_jobs_per_day"],
            applied_count=0,
            config=CONFIG,
            dry_run=CONFIG.get("dry_run", False),
            applied_urls=applied_urls,
        )
        if new_urls:
            add_applied_urls(tracker, new_urls)
        _autofill_all_tabs(driver, "Phase 2")
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 2] ✅ Done — {applied} Internshala applications")
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        _teardown(driver, "Phase 2")

    return applied


# ─────────────────────────────────────────────
#  PHASE 2: WEB SEARCH + ATS AUTO-APPLY
# ─────────────────────────────────────────────
def run_web_search_phase():
    """
    Phase 2: Web Search + ATS Auto-Apply
    - Google-searches for jobs on Lever, Greenhouse, Workday, career pages
    - For each result: navigates, clicks Apply, auto-fills form, uploads resume
    - Also opens job-board tabs via job_finder for manual review
    """
    phase_name = "Phase 6: Web Search + ATS Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    try:
        driver = create_driver("_websearch")
        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)

        print("  [Phase 6] 🌐 Finding jobs across the internet...")

        # Open job board tabs (Internshala, Naukri, Unstop, Google results)
        found_urls = job_finder.find_all_jobs(driver, CONFIG, applied_urls=applied_urls, max_tabs=20)
        if found_urls:
            add_applied_urls(tracker, found_urls)
        applied_urls = get_applied_urls(tracker)

        print(f"  [Phase 6] 📑 {len(found_urls)} job tabs opened")

        # Auto-apply on ATS/career pages via Google search
        print("  [Phase 6] 🤖 Running ATS auto-applier...")
        web_count, web_urls = web_search_applier.search_and_apply(driver, CONFIG, applied_urls)
        if web_urls:
            add_applied_urls(tracker, web_urls)
        applied += web_count

        print(f"  [Phase 6] ✅ ATS applied: {web_count}")

        # Auto-fill any forms that opened in new tabs during web search
        _autofill_all_tabs(driver, "Phase 6")

        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 6] ✅ Done — {applied} applications")

    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        # Tabs ALWAYS stay open so the user can review the web-search results
        # and apply manually later — this is the explicit Phase 2 contract.
        _teardown(driver, "Phase 6")

    return applied


# ─────────────────────────────────────────────
#  PHASE 3: FORM FILL — ALL OPEN TABS
# ─────────────────────────────────────────────
def run_form_fill_phase():
    """
    Phase 3: Smart Form Fill
    - Opens a fresh browser session
    - Scans EVERY open tab for forms:
        * Google Forms  → fill_google_form()
        * Standard HTML → fill_web_form()   (ATS, Typeform, JotForm, etc.)
    - Detects fields by: name, id, placeholder, aria-label, label text
    - Fills: name, email, phone, college, CGPA, experience, salary, location…
    - Uploads resume to every file input found
    - Fires React/Vue/Angular change events so values register in SPAs
    """
    phase_name = "Phase 7: Form Fill (All Tabs)"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    filled = 0

    try:
        driver = create_driver("_formfill")

        print("  [Phase 7] 📝 Scanning all open tabs for forms...")
        filled, total_fields = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        print(f"  [Phase 7] ✅ Filled {total_fields} fields across {filled} tabs")

        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=filled)

    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=filled, error=str(e))
        traceback.print_exc()
    finally:
        # Tabs ALWAYS stay open so the user can inspect what got filled and
        # hit submit manually if needed. No driver.quit().
        _teardown(driver, "Phase 7")

    return filled


# ─────────────────────────────────────────────
#  PHASE 4: WELLFOUND SEARCH + APPLY
# ─────────────────────────────────────────────
def run_wellfound_phase():
    """
    Phase 4: Wellfound
    - Login with Wellfound credentials
    - Search all intern keywords
    - Fill cover note (Gemini AI or template)
    - Click Apply on each matching job
    - Auto-fill any external form tabs that open + upload resume
    """
    phase_name = "Phase 3: Wellfound Search + Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    wf_email    = CONFIG.get("wellfound", {}).get("email", "")
    wf_password = CONFIG.get("wellfound", {}).get("password", "")

    if not wf_email or not wf_password or wf_password.startswith("YOUR_"):
        print("  [Phase 3] ❌ Wellfound credentials not set — skipping.")
        PERFORMANCE_TRACKER.end_phase(phase_name, error="No credentials")
        return 0

    try:
        driver = create_driver("_wellfound")

        print("  [Phase 3] 🔐 Logging into Wellfound...")
        login_ok = wellfound_applier.login(driver, wf_email, wf_password)
        if not login_ok:
            print("  [Phase 3] ❌ Wellfound login failed.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="Login failed")
            return 0

        print("  [Phase 3] ✅ Logged in — searching jobs...")
        applied, applied_urls = wellfound_applier.search_and_apply(
            driver,
            keywords=CONFIG["keywords"],
            locations=CONFIG["locations"],
            max_jobs=CONFIG["max_jobs_per_day"],
            applied_count=0,
            config=CONFIG,
            dry_run=CONFIG.get("dry_run", False),
            applied_urls=set()
        )

        # Auto-fill any external tabs Wellfound redirected to
        _autofill_all_tabs(driver, "Phase 3")

        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 3] ✅ Done — {applied} Wellfound applications")

    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        # Tabs ALWAYS stay open — same contract as every other phase.
        _teardown(driver, "Phase 3")

    return applied


# ─────────────────────────────────────────────
#  PHASE 4: NAUKRI AUTO-APPLY
# ─────────────────────────────────────────────
def run_naukri_phase():
    """Phase 4: Naukri search + apply."""
    phase_name = "Phase 4: Naukri Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    creds = CONFIG.get("naukri", {}) or {}
    email = creds.get("email", "")
    password = creds.get("password", "")
    if not email or not password or password.startswith("YOUR_"):
        print("  [Phase 4] ❌ Naukri credentials not set — skipping.")
        PERFORMANCE_TRACKER.end_phase(phase_name, error="No credentials")
        return 0

    try:
        driver = create_driver("_naukri")
        print("  [Phase 4] 🔐 Logging into Naukri...")
        if not other_platforms.naukri_login(driver, email, password):
            print("  [Phase 4] ❌ Naukri login failed.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="Login failed")
            return 0

        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)
        applied, new_urls = other_platforms.naukri_apply(
            driver,
            keywords=CONFIG["keywords"],
            locations=CONFIG["locations"],
            max_jobs=CONFIG["max_jobs_per_day"],
            applied_count=0,
            resume_path=CONFIG.get("resume_path", ""),
            config=CONFIG,
            dry_run=CONFIG.get("dry_run", False),
            applied_urls=applied_urls,
        )
        if new_urls:
            add_applied_urls(tracker, new_urls)
        _autofill_all_tabs(driver, "Phase 4")
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 4] ✅ Done — {applied} Naukri applications")
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        _teardown(driver, "Phase 4")

    return applied


# ─────────────────────────────────────────────
#  PHASE 5: UNSTOP AUTO-APPLY
# ─────────────────────────────────────────────
def run_unstop_phase():
    """Phase 5: Unstop search + apply."""
    phase_name = "Phase 5: Unstop Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0

    creds = CONFIG.get("unstop", {}) or {}
    email = creds.get("email", "")
    password = creds.get("password", "")
    if not email or not password or password.startswith("YOUR_"):
        print("  [Phase 5] ❌ Unstop credentials not set — skipping.")
        PERFORMANCE_TRACKER.end_phase(phase_name, error="No credentials")
        return 0

    try:
        driver = create_driver("_unstop")
        print("  [Phase 5] 🔐 Logging into Unstop...")
        if not other_platforms.unstop_login(driver, email, password):
            print("  [Phase 5] ❌ Unstop login failed.")
            PERFORMANCE_TRACKER.end_phase(phase_name, error="Login failed")
            return 0

        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)
        applied, new_urls = other_platforms.unstop_apply(
            driver,
            keywords=CONFIG["keywords"],
            locations=CONFIG["locations"],
            max_jobs=CONFIG["max_jobs_per_day"],
            applied_count=0,
            config=CONFIG,
            dry_run=CONFIG.get("dry_run", False),
            applied_urls=applied_urls,
        )
        if new_urls:
            add_applied_urls(tracker, new_urls)
        _autofill_all_tabs(driver, "Phase 5")
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
        print(f"  [Phase 5] ✅ Done — {applied} Unstop applications")
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
        traceback.print_exc()
    finally:
        _teardown(driver, "Phase 5")

    return applied


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    import sys

    print("=" * 60)
    print("🤖 JOB AUTO-APPLIER — CONCURRENT ORCHESTRATOR")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    print("📌 Phase 1 — LinkedIn Auto-Apply (Easy Apply + External forms)")
    print("📌 Phase 2 — Internshala Auto-Apply")
    print("📌 Phase 3 — Wellfound Search + Apply")
    print("📌 Phase 4 — Naukri Auto-Apply")
    print("📌 Phase 5 — Unstop Auto-Apply")
    print("📌 Phase 6 — Web Search + ATS Auto-Apply (Lever/Greenhouse/Workday)")
    print("📌 Phase 7 — Form Fill: scan all tabs, detect & fill every form")
    print("=" * 60)

    # Map phase number → function
    phase_map = {
        1: run_linkedin_phase,
        2: run_internshala_phase,
        3: run_wellfound_phase,
        4: run_naukri_phase,
        5: run_unstop_phase,
        6: run_web_search_phase,
        7: run_form_fill_phase,
    }

    # Allow running specific phases: python orchestrator.py 1 4
    if len(sys.argv) > 1:
        chosen = [int(x) for x in sys.argv[1:] if x.isdigit() and int(x) in phase_map]
        phases = [phase_map[n] for n in sorted(set(chosen))]
        print(f"🎯 Running phases: {sorted(set(chosen))}")
    else:
        phases = list(phase_map.values())
        print("🎯 Running ALL phases concurrently")

    print("=" * 60)

    import concurrent.futures
    with ThreadPoolExecutor(max_workers=len(phases)) as executor:
        futures = {executor.submit(fn): fn.__name__ for fn in phases}
        # The user instructed to wrap future.result() with a 600s timeout.
        # Doing this directly on the futures items ensures the timeout applies to the task runtime.
        for future, name in futures.items():
            try:
                result = future.result(timeout=600)
                print(f"\n[{name}] ✅ Completed — result: {result}")
            except concurrent.futures.TimeoutError:
                print(f"\n[{name}] 🛑 Failed: 10-minute timeout exceeded.")
            except Exception as e:
                print(f"\n[{name}] ❌ Failed: {e}")
                traceback.print_exc()

    PERFORMANCE_TRACKER.summary()
    COST_OPTIMIZER.summary()

    print("\n" + "=" * 60)
    print("✅ ALL PHASES COMPLETE")
    print("👉 Check your browser tabs for any forms needing manual review")
    print("=" * 60)


if __name__ == "__main__":
    main()
