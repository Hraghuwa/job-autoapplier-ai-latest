"""
🧠 Multi-Agent Orchestrator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Executes Job Application Phases concurrently using ThreadPoolExecutor
to optimize throughput and reduce total run time.
"""

import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import CONFIG
from utils.performance import PERFORMANCE_TRACKER, COST_OPTIMIZER

import linkedin_applier
import job_finder
import google_form_filler
import web_search_applier
import linkedin_outreach
import wellfound_applier
import other_platforms
from main import load_tracker, save_tracker, get_applied_urls, add_applied_urls

def create_driver():
    opts = Options()
    # Remove --start-maximized to avoid stealing full screen focus
    opts.add_argument("--window-size=1200,800")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    # Headless can be configured if needed, but for CAPTCHAs we keep it headed
    # opts.add_argument("--headless")
    opts.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Try to lower the window so it doesn't pop up directly in user's face
    try:
        driver.set_window_position(50, 50)
    except:
        pass
        
    return driver

def run_linkedin_phase():
    phase_name = "Phase 1: LinkedIn Auto-Apply"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0
    try:
        driver = create_driver()
        
        linkedin_pwd = CONFIG.get("linkedin", {}).get("password", "")
        linkedin_email = CONFIG.get("linkedin", {}).get("email", "")
        
        if linkedin_email and linkedin_pwd and not linkedin_pwd.startswith("YOUR_"):
            print("  [Phase 1] 🔐 Logging into LinkedIn...")
            login_ok = linkedin_applier.login(driver, linkedin_email, linkedin_pwd)
            if not login_ok:
                print("  [Phase 1] ❌ Login failed.")
                PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error="Login failed")
                driver.quit()
                return 0
        
        agents = CONFIG.get("role_agents", [])
        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)
        
        for a in agents:
            cfg = dict(CONFIG)
            cfg["keywords"] = a["keywords"]
            applied += linkedin_applier.run(driver, cfg, 0, CONFIG["max_jobs_per_day"], applied_urls=applied_urls)
        
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return applied

def run_web_search_and_fill_phase():
    phase_name = "Phase 2 & 3: Web Search + Form Fill"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0
    try:
        driver = create_driver()
        tracker = load_tracker()
        applied_urls = get_applied_urls(tracker)
        
        # 1. Open tabs with job finding (Max 20 tabs per run, tracked via applied_urls)
        found_urls = job_finder.find_all_jobs(driver, CONFIG, applied_urls=applied_urls, max_tabs=20)
        
        # Add found URLs to tracker so they aren't shown again
        if found_urls:
            add_applied_urls(tracker, found_urls)
            
        applied_urls = get_applied_urls(tracker) # reload
        
        # 2. Apply on web search auto applier
        web_count, web_urls = web_search_applier.search_and_apply(driver, CONFIG, applied_urls)
        if web_urls:
            add_applied_urls(tracker, web_urls)
            
        # 3. Fill forms
        filled_count, _ = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        
        applied = web_count + filled_count
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return applied

def run_outreach_phase():
    phase_name = "Phase 4: LinkedIn Outreach"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    sent = 0
    try:
        driver = create_driver()
        
        linkedin_pwd = CONFIG.get("linkedin", {}).get("password", "")
        linkedin_email = CONFIG.get("linkedin", {}).get("email", "")
        
        if linkedin_email and linkedin_pwd and not linkedin_pwd.startswith("YOUR_"):
            print("  [Phase 4] 🔐 Logging into LinkedIn...")
            linkedin_applier.login(driver, linkedin_email, linkedin_pwd)
            time.sleep(3)
        
        sent, _, _ = linkedin_outreach.run_outreach(driver, CONFIG)
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=sent)
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=sent, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return sent

def run_wellfound_phase():
    phase_name = "Phase 5: Wellfound Connect"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0
    
    wf_config = CONFIG.get("wellfound", {})
    email = wf_config.get("email", "")
    password = wf_config.get("password", "")
    
    if not email or not password or password.startswith("YOUR_"):
        PERFORMANCE_TRACKER.end_phase(phase_name, error="No Wellfound Credentials")
        return 0
        
    try:
        driver = create_driver()
        login_ok = wellfound_applier.login(driver, email, password)
        if login_ok:
            applied, _ = wellfound_applier.search_and_apply(
                driver, 
                keywords=CONFIG["keywords"],
                locations=CONFIG["locations"],
                max_jobs=CONFIG["max_jobs_per_day"],
                applied_count=0,
                config=CONFIG,
                dry_run=CONFIG.get("dry_run", False),
                applied_urls=set()
            )
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
def run_other_platforms_phase():
    phase_name = "Phase 3: Unstop / Naukri"
    PERFORMANCE_TRACKER.start_phase(phase_name)
    driver = None
    applied = 0
    try:
        driver = create_driver()
        email = CONFIG.get("profile", {}).get("email", "")
        pwd = CONFIG.get("profile", {}).get("password", "YOUR_PASSWORD")
        
        # Naukri Login & Apply
        other_platforms.naukri_login(driver, email, pwd)
        n_count, n_urls = other_platforms.naukri_apply(
            driver, CONFIG["keywords"], CONFIG["locations"], 
            CONFIG["max_jobs_per_day"], 0, config=CONFIG
        )
        applied += n_count
        
        # Unstop Login & Apply
        other_platforms.unstop_login(driver, email, pwd)
        u_count, u_urls = other_platforms.unstop_apply(
            driver, CONFIG["keywords"], CONFIG["locations"], 
            CONFIG["max_jobs_per_day"], 0, config=CONFIG
        )
        applied += u_count
        
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied)
    except Exception as e:
        PERFORMANCE_TRACKER.end_phase(phase_name, jobs_applied=applied, error=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return applied

def main():
    print("=" * 60)
    print("🤖 JOB AUTO-APPLIER — CONCURRENT ORCHESTRATOR")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("🚀 Launching multi-agent execution...")
    print("=" * 60)

    import sys
    
    # Run phases concurrently
    all_phases = [
        run_linkedin_phase,
        run_web_search_and_fill_phase,
        run_outreach_phase,
        run_wellfound_phase,
        run_other_platforms_phase
    ]
    
    phases = []
    
    if len(sys.argv) > 1:
        # User specified phases to run (e.g. python3 orchestrator.py 1 5)
        allowed_nums = [int(x) for x in sys.argv[1:] if x.isdigit()]
        if 1 in allowed_nums: phases.append(run_linkedin_phase)
        if 2 in allowed_nums: phases.append(run_web_search_and_fill_phase)
        if 3 in allowed_nums: phases.append(run_other_platforms_phase)
        if 4 in allowed_nums: phases.append(run_outreach_phase)
        if 5 in allowed_nums: phases.append(run_wellfound_phase)
        print(f"🎯 Running ONLY specified phases: {allowed_nums}")
    else:
        # Default: run all
        phases = all_phases
        print("🎯 Running ALL phases automatically")
    
    with ThreadPoolExecutor(max_workers=len(phases)) as executor:
        futures = {executor.submit(phase): phase.__name__ for phase in phases}
        
        for future in as_completed(futures):
            phase_name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"❌ Unhandled Exception in {phase_name}: {e}")
                traceback.print_exc()

    # Print summary reports
    PERFORMANCE_TRACKER.summary()
    COST_OPTIMIZER.summary()

if __name__ == "__main__":
    main()
