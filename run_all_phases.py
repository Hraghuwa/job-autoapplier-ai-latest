"""
🤖 Run ALL Phases — 15 minutes each, Phase to Phase
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1: LinkedIn Auto-Apply (AI-powered)     — 15 min
Phase 2: Internshala Auto-Apply               — 15 min
Phase 3: Wellfound Auto-Apply                 — 15 min
Phase 4: Naukri Auto-Apply                    — 15 min
Phase 5: Unstop Auto-Apply                    — 15 min
Phase 6: Unified Web Discovery & Auto-Apply   — 15 min
Phase 7: Smart Form Fill (Remaining Tabs)     — 15 min
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total runtime: ~105 minutes
"""

import time
import traceback
import threading
import sys
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import CONFIG
import linkedin_applier
import job_finder
import google_form_filler
import web_search_applier
import wellfound_applier
import internshala_applier
import other_platforms

PHASE_TIMEOUT = 15 * 60  # 15 minutes per phase


# ─────────────────────────────────────────────
#  BROWSER SETUP
# ─────────────────────────────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    
    username = CONFIG.get("username", "default")
    profile_path = os.path.abspath(f"chrome_profile_{username}")
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = os.path.join(profile_path, lock_file)
        try:
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    opts.add_argument(f"--user-data-dir={profile_path}")
    
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# ─────────────────────────────────────────────
#  TIMEOUT WRAPPER
# ─────────────────────────────────────────────
class PhaseTimeout(Exception):
    pass


def run_with_timeout(func, args, timeout_sec, phase_name):
    """Run a function with a timeout. Returns the result or None on timeout."""
    result = [None]
    error = [None]

    def target():
        try:
            result[0] = func(*args)
        except PhaseTimeout:
            pass
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        print(f"\n  ⏰ {phase_name}: 15 minutes reached — moving to next phase")
        return result[0]

    if error[0]:
        print(f"  ❌ {phase_name} error: {error[0]}")
        traceback.print_exc()

    return result[0]


# ─────────────────────────────────────────────
#  PHASE HANDLERS (Aligned 1-7)
# ─────────────────────────────────────────────

def phase1_linkedin(driver):
    li_config = CONFIG.get("linkedin", {})
    email = li_config.get("email", "")
    password = li_config.get("password", "")
    cookies_json = CONFIG.get("linkedin_cookies", "")

    has_pwd = email and password and not password.startswith("YOUR_")
    has_cookies = bool(cookies_json)

    if not has_pwd and not has_cookies:
        print("  ❌ Skipping: No LinkedIn credentials or cookies in config.py")
        return 0

    try:
        login_ok = linkedin_applier.login(driver, email, password)
        if not login_ok:
            print("  ❌ LinkedIn login failed.")
            return 0
    except Exception as e:
        print(f"  ❌ LinkedIn Login Error: {e}")
        return 0

    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()
    for i, agent in enumerate(agents, 1):
        if time.time() - start >= PHASE_TIMEOUT - 30: break
        cfg = dict(CONFIG); cfg["keywords"] = agent["keywords"]
        try:
            count = linkedin_applier.run(driver, cfg, 0, CONFIG["max_jobs_per_day"], applied_urls=set())
            total += count
        except: pass
    return total

def phase2_internshala(driver):
    ish_config = CONFIG.get("internshala", {})
    if not ish_config.get("email"): return 0
    try:
        internshala_applier.login(driver, ish_config["email"], ish_config["password"])
        return internshala_applier.run(driver, CONFIG, 0, 10, set())
    except: return 0

def phase3_wellfound(driver):
    wf_config = CONFIG.get("wellfound", {})
    if not wf_config.get("email"): return 0
    try:
        wellfound_applier.login(driver, wf_config["email"], wf_config["password"])
        return wellfound_applier.run(driver, CONFIG, 0, 10, set())
    except: return 0

def phase4_naukri(driver):
    naukri_config = CONFIG.get("naukri", {})
    if not naukri_config.get("email"): return 0
    try:
        other_platforms.naukri_login(driver, naukri_config["email"], naukri_config.get("password", ""))
        count, _ = other_platforms.naukri_apply(driver, CONFIG.get("keywords", []), CONFIG["locations"], 10, 0, config=CONFIG)
        return count
    except: return 0

def phase5_unstop(driver):
    unstop_config = CONFIG.get("unstop", {})
    if not unstop_config.get("email"): return 0
    try:
        other_platforms.unstop_login(driver, unstop_config["email"], unstop_config.get("password", ""))
        count, _ = other_platforms.unstop_apply(driver, CONFIG.get("keywords", []), CONFIG["locations"], 10, 0, config=CONFIG)
        return count
    except: return 0

def phase6_web(driver):
    """INTEGRATED DISCOVERY ENGINE: Search + Auto-Apply."""
    print("\n  🚀 Running Unified Web Discovery & Auto-Apply...")
    try:
        # Superior query engine from job_finder + vision-based applier
        applied_count, urls = web_search_applier.search_and_apply(driver, CONFIG, set())
        return len(urls), applied_count
    except Exception as e:
        print(f"  ⚠️ Web search error: {e}")
        return 0, 0

def phase7_fill(driver):
    """Fill all remaining open tabs from discovery."""
    try:
        filled, _ = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        return filled
    except: return 0


# ─────────────────────────────────────────────
#  MAIN EXECUTION LOOP
# ─────────────────────────────────────────────
if __name__ == "__main__":
    CYCLE_DELAY_MINUTES = CONFIG.get("cycle_delay_minutes", 30)

    while True:
        total_start = time.time()
        print("\n" + "="*60)
        print("🤖 JOB AUTO-APPLIER v6 — INTEGRATED DISCOVERY")
        print("="*60)
        
        results = {"li":0, "ish":0, "wf":0, "nk":0, "us":0, "found":0, "web":0, "fill":0}
        
        # Phase 1: LinkedIn
        d1 = create_driver()
        results["li"] = run_with_timeout(phase1_linkedin, (d1,), PHASE_TIMEOUT, "LinkedIn") or 0
        d1.quit()

        # Phase 2: Internshala
        d2 = create_driver()
        results["ish"] = run_with_timeout(phase2_internshala, (d2,), PHASE_TIMEOUT, "Internshala") or 0
        d2.quit()

        # Phase 3: Wellfound
        d3 = create_driver()
        results["wf"] = run_with_timeout(phase3_wellfound, (d3,), PHASE_TIMEOUT, "Wellfound") or 0
        d3.quit()

        # Phase 4: Naukri
        d4 = create_driver()
        results["nk"] = run_with_timeout(phase4_naukri, (d4,), PHASE_TIMEOUT, "Naukri") or 0
        d4.quit()

        # Phase 5: Unstop
        d5 = create_driver()
        results["us"] = run_with_timeout(phase5_unstop, (d5,), PHASE_TIMEOUT, "Unstop") or 0
        d5.quit()

        # Phase 6 & 7: Web Discovery & Fill (Keep browser open)
        d6 = create_driver()
        res6 = run_with_timeout(phase6_web, (d6,), PHASE_TIMEOUT, "Web Discovery")
        if res6: results["found"], results["web"] = res6
        
        results["fill"] = run_with_timeout(phase7_fill, (d6,), PHASE_TIMEOUT, "Form Fill") or 0
        
        # FINAL SUMMARY
        print("\n" + "="*60)
        print(f"🎉 CYCLE COMPLETE! Duration: {(time.time()-total_start)//60}m")
        print("="*60)
        print(f"🔗 LinkedIn: {results['li']} | 🎓 Internshala: {results['ish']} | 🚀 Wellfound: {results['wf']}")
        print(f"💼 Naukri: {results['nk']} | 🎯 Unstop: {results['us']}")
        print(f"🌐 Web Found: {results['found']} | ✅ Auto-Applied: {results['web']} | 📝 Form Filled: {results['fill']}")
        print("="*60)
        print(f"\n⏳ Waiting {CYCLE_DELAY_MINUTES}m...")
        time.sleep(CYCLE_DELAY_MINUTES * 60)
