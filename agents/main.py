"""
🤖 Job Auto-Applier — AI-POWERED MULTI-AGENT (v4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1: LINKEDIN AUTO-APPLY (AI-powered form filling)
   Each role agent auto-applies on LinkedIn
   Gemini AI answers unknown form fields intelligently

PHASE 2: JOB FINDER + WEB SEARCH APPLIER
   2A: Opens jobs in tabs from Internshala, Unstop, Naukri, Google
   2B: Web Search Auto-Applier — searches ATS/career pages & auto-applies

PHASE 3: AUTO-FILL FORMS
   Scans all opened tabs for Google Forms & web forms
   Auto-fills fields + uploads resume

PHASE 3: AUTO-FILL FORMS
   Scans all opened tabs for Google Forms & web forms
   Auto-fills fields + uploads resume

Location: Bangalore / Bengaluru / Remote
"""

import time
import json
import os
import traceback
from datetime import datetime, timedelta
# selenium kept for fallback only — undetected_chromedriver is the primary driver
from selenium import webdriver

from config import CONFIG
import linkedin_applier
import job_finder
import google_form_filler
import web_search_applier


# ─────────────────────────────────────────────
#  TRACKER
# ─────────────────────────────────────────────
TRACKER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applied_jobs.json")

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE) as f:
            data = json.load(f)
        if "applied_urls" not in data:
            data["applied_urls"] = []
        return data
    return {"total": 0, "cycles": 0, "jobs": [], "applied_urls": []}

def save_tracker(tracker):
    with open(TRACKER_FILE, "w") as f:
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(tracker, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
        except ImportError:
            # fcntl not available on Windows — write without lock
            # Sequential execution (Fix 6) makes this safe in practice
            json.dump(tracker, f, indent=2)

def get_applied_urls(tracker):
    return set(tracker.get("applied_urls", []))

def add_applied_urls(tracker, new_urls):
    existing = set(tracker.get("applied_urls", []))
    for url in new_urls:
        if url and url not in existing:
            tracker.setdefault("applied_urls", []).append(url)
            existing.add(url)
    save_tracker(tracker)


# ─────────────────────────────────────────────
#  BROWSER SETUP
# ─────────────────────────────────────────────
def create_driver(headless=False):
    """
    Create a Chrome driver using undetected-chromedriver to bypass bot detection.
    headless=False by default — runs as a visible window on the user's machine,
    which is the only reliable way to pass LinkedIn / Naukri / Internshala security checks.
    """
    try:
        import undetected_chromedriver as uc
        print("  🌐 Launching undetected-chromedriver...")
        options = uc.ChromeOptions()
        # Never run headless — visible browser on user's machine bypasses all security checks
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--start-maximized")   # Use maximized to ensure visibility
        
        # Bypass some common blocks
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")

        # Detect Chrome version to avoid UC mismatch
        import subprocess
        chrome_version = None
        try:
            proc = subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'], stdout=subprocess.PIPE)
            out, _ = proc.communicate()
            chrome_version = int(out.decode('utf-8').split()[-1].split('.')[0])
        except:
            pass

        kwargs = {"options": options, "use_subprocess": True}
        if chrome_version:
            kwargs["version_main"] = chrome_version

        driver = uc.Chrome(**kwargs)
        print("  ✅ Browser launched successfully.")
        time.sleep(2)
        return driver
    except Exception as _uc_err:
        # Fallback to regular selenium if undetected-chromedriver not installed or fails
        print(f"  ⚠️  undetected-chromedriver failed: {_uc_err}")
        print("  🔄 Falling back to standard Selenium driver...")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import glob as _glob

        options = Options()
        _UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36")
        options.add_argument(f"--user-agent={_UA}")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            wdm_path = ChromeDriverManager().install()
            driver_dir = os.path.dirname(wdm_path)
            candidates = _glob.glob(os.path.join(driver_dir, "chromedriver*"))
            binary = next((p for p in candidates if os.path.isfile(p) and "NOTICES" not in p), wdm_path)
            os.chmod(binary, 0o755)
            driver = webdriver.Chrome(service=Service(binary), options=options)
            
            print("  ✅ Standard Selenium driver launched.")
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source":
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                })
            except Exception:
                pass
            time.sleep(2)
            return driver
        except Exception as _e2:
            print(f"  ❌ Critical error: All driver launch attempts failed: {_e2}")
            raise _e2



def safe_quit(driver):
    """
    Never forcefully close the browser.
    The user wants to see where the agent stopped or what it applied to.
    The Chrome window stays open until the user manually closes it.
    """
    print("  🌐 Browser session preserved — window left open for review.")


# ─────────────────────────────────────────────
#  PHASE 1: LINKEDIN AUTO-APPLY (per agent)
# ─────────────────────────────────────────────
def run_linkedin_agent(agent, agent_num, total_agents, tracker, shared_driver=None):
    """Run one role agent on LinkedIn only. Auto-applies.
    If shared_driver is provided, reuses it (no new login needed).
    """
    agent_name = agent["name"]
    agent_emoji = agent.get("emoji", "🔹")
    agent_keywords = agent["keywords"]

    print(f"\n{'▓' * 60}")
    print(f"  {agent_emoji} LINKEDIN AGENT {agent_num}/{total_agents}: {agent_name}")
    print(f"  📋 Keywords: {', '.join(agent_keywords)}")
    print(f"{'▓' * 60}")

    agent_config = dict(CONFIG)
    agent_config["keywords"] = agent_keywords

    applied_urls = get_applied_urls(tracker)
    applied_count = 0
    owns_driver = shared_driver is None  # only quit if we created it

    linkedin_pwd = CONFIG["linkedin"]["password"]
    if not linkedin_pwd or linkedin_pwd.startswith("YOUR_"):
        print(f"  [LinkedIn] ⏭️  Skipping (password not set).")
        return 0

    driver = shared_driver
    try:
        if driver is None:
            driver = create_driver(headless=CONFIG.get("headless", False))
            print(f"  [LinkedIn] 🔐 Logging in...")
            login_ok = linkedin_applier.login(
                driver, CONFIG["linkedin"]["email"], linkedin_pwd
            )
            if not login_ok:
                print(f"  [LinkedIn] ⏭️  Login failed, skipping.")
                safe_quit(driver)
                return 0
        else:
            print(f"  [LinkedIn] ♻️  Reusing existing browser session...")

        print(f"  [LinkedIn] 🎯 Applying to {agent_name} roles...")
        applied_count = linkedin_applier.run(
            driver, agent_config, 0, CONFIG["max_jobs_per_day"],
            applied_urls=applied_urls
        )

        print(f"  ✅ LinkedIn ({agent_name}): Applied to {applied_count} jobs")

    except Exception as e:
        print(f"  ❌ LinkedIn error: {e}")
        traceback.print_exc()

    finally:
        if owns_driver and driver:
            safe_quit(driver)

    return applied_count


# ─────────────────────────────────────────────
#  PHASE 2: JOB FINDER (open tabs, no auto-apply)
# ─────────────────────────────────────────────
def run_job_finder(tracker):
    """
    Search across all platforms for jobs.
    Opens found jobs in browser tabs.
    Returns (driver, found_count) — driver kept alive for Phase 3.
    """
    print(f"\n{'█' * 60}")
    print(f"  🔍 PHASE 2: INTENSIVE JOB FINDER")
    print(f"  📑 Opening jobs in tabs")
    print(f"  🌐 Browser will STAY OPEN")
    print(f"{'█' * 60}")

    applied_urls = get_applied_urls(tracker)
    driver = None

    try:
        driver = create_driver(headless=False)  # Always visible
        print(f"  🌐 Browser started (will stay open)")

        # Search all platforms and open in tabs (limit 20 per run)
        found_urls = job_finder.find_all_jobs(driver, CONFIG, applied_urls, max_tabs=20)

        # Track found URLs so they are skipped next run
        if found_urls:
            add_applied_urls(tracker, found_urls)

        tabs = len(driver.window_handles) if job_finder.is_driver_alive(driver) else 0
        print(f"\n  🎉 Phase 2 done! {tabs} tabs open.")

        # Return driver alive for Phase 3
        return driver, len(found_urls)

    except Exception as e:
        print(f"  ❌ Job Finder error: {e}")
        traceback.print_exc()
        return driver, 0


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    agents = CONFIG.get("role_agents", [])

    print("=" * 60)
    print("🤖 JOB AUTO-APPLIER v4 (AI-Powered)")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n📌 PHASE 1: LinkedIn Auto-Apply (AI form filling)")
    print(f"   {len(agents)} role agents with Gemini AI")
    for a in agents:
        print(f"     {a.get('emoji', '🔹')} {a['name']}")
    print(f"\n📌 PHASE 2: Job Finder + Web Search Auto-Applier")
    print(f"   2A: Open jobs in tabs from all platforms")
    print(f"   2B: Auto-apply on ATS/career pages")
    print(f"\n📌 PHASE 3: Auto-Fill Forms + Upload Resume")
    print(f"\n📍 Location: {', '.join(CONFIG['locations'])}")
    print(f"📄 Resume: {CONFIG['resume_path'].split('/')[-1]}")
    print("=" * 60)

    # Validate resume
    if not os.path.exists(CONFIG["resume_path"]):
        print(f"\n❌ Resume not found at '{CONFIG['resume_path']}'")
        return

    tracker = load_tracker()
    print(f"\n📊 Previously applied: {len(get_applied_urls(tracker))} unique URLs\n")

    total_applied = 0

    # ════════════════════════════════════════════
    # PHASE 1: LinkedIn Auto-Apply (each agent)
    # ════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print(f"  📌 PHASE 1: LINKEDIN AUTO-APPLY")
    print(f"{'═' * 60}")

    for i, agent in enumerate(agents, 1):
        count = run_linkedin_agent(agent, i, len(agents), tracker)
        total_applied += count
        if i < len(agents):
            print(f"\n  ⏳ Next agent in 5s...")
            time.sleep(5)

    print(f"\n  ✅ PHASE 1 COMPLETE: {total_applied} LinkedIn applications")

    # ════════════════════════════════════════════
    # PHASE 2: Job Finder (open tabs)
    # ════════════════════════════════════════════
    print(f"\n{'═' * 60}")
    print(f"  📌 PHASE 2: INTENSIVE JOB FINDER — Opening tabs")
    print(f"{'═' * 60}")

    finder_driver, found_count = run_job_finder(tracker)

    # ════════════════════════════════════════════
    # PHASE 2B: Web Search Auto-Applier
    # ════════════════════════════════════════════
    web_applied = 0
    if finder_driver and job_finder.is_driver_alive(finder_driver):
        print(f"\n{'═' * 60}")
        print(f"  🌐 PHASE 2B: WEB SEARCH AUTO-APPLIER")
        print(f"{'═' * 60}")

        try:
            web_applied, web_urls = web_search_applier.search_and_apply(
                finder_driver, CONFIG, get_applied_urls(tracker)
            )
            if web_urls:
                add_applied_urls(tracker, web_urls)
        except Exception as e:
            print(f"  ❌ Web search apply error: {e}")
            traceback.print_exc()

    # ════════════════════════════════════════════
    # PHASE 3: Auto-Fill Forms + Upload Resume
    # ════════════════════════════════════════════
    filled_tabs = 0
    if finder_driver and job_finder.is_driver_alive(finder_driver):
        print(f"\n{'═' * 60}")
        print(f"  📌 PHASE 3: AUTO-FILL FORMS + UPLOAD RESUME")
        print(f"{'═' * 60}")

        try:
            filled_tabs, total_fields = google_form_filler.auto_fill_open_tabs(
                finder_driver, CONFIG
            )
        except Exception as e:
            print(f"  ❌ Auto-fill error: {e}")
            traceback.print_exc()

        tabs = len(finder_driver.window_handles) if job_finder.is_driver_alive(finder_driver) else 0
        print(f"\n  🎉 Phases 2-3 done! {tabs} tabs open.")
        print(f"  👉 Review filled forms and submit manually.")
        print(f"  ⚠️  Browser stays open — take your time!")


    tracker["total"] = tracker.get("total", 0) + total_applied
    tracker["cycles"] = tracker.get("cycles", 0) + 1
    tracker["last_run"] = datetime.now().isoformat()
    save_tracker(tracker)

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"✅ ALL DONE! (AI-powered v4)")
    print(f"📊 LinkedIn auto-applied: {total_applied}")
    print(f"📑 Jobs opened in tabs: {found_count}")
    print(f"🌐 Web search applied: {web_applied}")
    print(f"📝 Forms auto-filled: {filled_tabs}")
    print(f"📊 Total tracked URLs: {len(get_applied_urls(tracker))}")
    print(f"👉 Go to your browser — review and submit!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
