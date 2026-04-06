"""
🤖 Run ALL Phases — 15 minutes each, Phase to Phase
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1: LinkedIn Auto-Apply (AI-powered)     — 15 min
Phase 2: Job Finder + Web Search Applier      — 15 min
Phase 3: Auto-Fill Forms + Resume Upload      — 15 min
Phase 4: LinkedIn Outreach (GenAI messages)   — 15 min
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total runtime: ~60 minutes
"""

import time
import traceback
import threading
import sys
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

PHASE_TIMEOUT = 15 * 60  # 15 minutes per phase


# ─────────────────────────────────────────────
#  BROWSER SETUP
# ─────────────────────────────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
    
    import os
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
        # Thread is daemon so it'll be abandoned when next phase starts
        return result[0]

    if error[0]:
        print(f"  ❌ {phase_name} error: {error[0]}")
        traceback.print_exc()

    return result[0]


# ─────────────────────────────────────────────
#  PHASE 1: LinkedIn Auto-Apply
# ─────────────────────────────────────────────
def phase1_linkedin(driver):
    """Run all LinkedIn agents. Stops when main thread timeout kills it."""
    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()

    for i, agent in enumerate(agents, 1):
        elapsed = time.time() - start
        if elapsed >= PHASE_TIMEOUT - 30:
            break

        remaining = int(PHASE_TIMEOUT - elapsed)
        print(f"\n  {'▓' * 55}")
        print(f"  {agent.get('emoji', '🔹')} AGENT {i}/{len(agents)}: {agent['name']}")
        print(f"  📋 {', '.join(agent['keywords'])}")
        print(f"  ⏰ {remaining // 60}m {remaining % 60}s left")
        print(f"  {'▓' * 55}")

        cfg = dict(CONFIG)
        cfg["keywords"] = agent["keywords"]

        try:
            count = linkedin_applier.run(
                driver, cfg, 0, CONFIG["max_jobs_per_day"], applied_urls=set()
            )
            total += count
            print(f"  ✅ {agent['name']}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ {agent['name']} error: {str(e)[:50]}")

    return total


# ─────────────────────────────────────────────
#  PHASE 2: Job Finder + Web Search Applier
# ─────────────────────────────────────────────
def phase2_jobs(driver):
    """Search for jobs and auto-apply via web search."""
    start = time.time()

    # 2A: Job Finder — open tabs (first 7 min)
    print("\\n  📑 Phase 2A: Job Finder — opening tabs...")
    found_urls = []
    try:
        found_urls = job_finder.find_all_jobs(driver, CONFIG, set(), max_tabs=30)
    except Exception as e:
        print(f"  ⚠️  Job finder error: {str(e)[:50]}")

    tabs = len(driver.window_handles)
    print(f"  📊 Phase 2A done: {tabs} tabs, {len(found_urls)} jobs found")

    # 2B: Web Search Auto-Applier (remaining time)
    elapsed = time.time() - start
    if elapsed < PHASE_TIMEOUT - 60:
        print(f"\n  🌐 Phase 2B: Web Search Auto-Applier...")
        try:
            web_count, web_urls = web_search_applier.search_and_apply(
                driver, CONFIG, set()
            )
            print(f"  📊 Phase 2B done: {web_count} auto-applied")
            return len(found_urls), web_count
        except Exception as e:
            print(f"  ⚠️  Web search error: {str(e)[:50]}")

    return len(found_urls), 0


# ─────────────────────────────────────────────
#  PHASE 3: Auto-Fill Forms
# ─────────────────────────────────────────────
def phase3_fill(driver):
    """Fill all open form tabs."""
    try:
        filled, fields = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        return filled
    except Exception as e:
        print(f"  ❌ Auto-fill error: {str(e)[:50]}")
        return 0


# ─────────────────────────────────────────────
#  PHASE 4: Wellfound
# ─────────────────────────────────────────────
def phase4_wellfound(driver):
    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()
    
    wf_config = CONFIG.get("wellfound", {})
    if not wf_config.get("email") or not wf_config.get("password"):
        print("  ⏭️  Skipping Wellfound: Credentials missng")
        return 0

    try:
        wellfound_applier.login(driver, wf_config["email"], wf_config["password"])
    except Exception as e:
        print(f"  ⏭️  Wellfound login failed: {e}")
        return 0

    for i, agent in enumerate(agents, 1):
        elapsed = time.time() - start
        if elapsed >= PHASE_TIMEOUT - 30:
            break

        cfg = dict(CONFIG)
        cfg["keywords"] = agent["keywords"]

        try:
            count = wellfound_applier.run(driver, cfg, 0, 10, set())
            total += count
            print(f"  ✅ Wellfound {agent['name']}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ Wellfound error: {e}")

    return total


# ─────────────────────────────────────────────
#  PHASE 5: Internshala
# ─────────────────────────────────────────────
def phase5_internshala(driver):
    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()
    
    ish_config = CONFIG.get("internshala", {})
    if not ish_config.get("email") or not ish_config.get("password"):
        print("  ⏭️  Skipping Internshala: Credentials missing")
        return 0

    try:
        internshala_applier.login(driver, ish_config["email"], ish_config["password"])
    except Exception as e:
        print(f"  ⏭️  Internshala login failed: {e}")
        return 0

    for i, agent in enumerate(agents, 1):
        elapsed = time.time() - start
        if elapsed >= PHASE_TIMEOUT - 30:
            break

        cfg = dict(CONFIG)
        cfg["keywords"] = agent["keywords"]

        try:
            count = internshala_applier.run(driver, cfg, 0, 10, set())
            total += count
            print(f"  ✅ Internshala {agent['name']}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ Internshala error: {e}")

    return total


# ─────────────────────────────────────────────
#  PHASE 6: Unstop
# ─────────────────────────────────────────────
def phase6_unstop(driver):
    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()
    
    unstop_config = CONFIG.get("unstop", {})
    if not unstop_config.get("email"):
        print("  ⏭️  Skipping Unstop: Email missing")
        return 0

    try:
        # Use Google login if password isn't set, or email/pass if it is
        other_platforms.unstop_login(driver, unstop_config["email"], unstop_config.get("password", ""))
    except Exception as e:
        print(f"  ⏭️  Unstop login failed: {e}")
        return 0

    for i, agent in enumerate(agents, 1):
        elapsed = time.time() - start
        if elapsed >= PHASE_TIMEOUT - 30:
            break

        try:
            count, _ = other_platforms.unstop_apply(
                driver, agent["keywords"], CONFIG["locations"], 10, total, 
                config=CONFIG, dry_run=CONFIG.get("dry_run", False)
            )
            total = count
            print(f"  ✅ Unstop {agent['name']}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ Unstop error: {e}")

    return total


# ─────────────────────────────────────────────
#  PHASE 7: Naukri
# ─────────────────────────────────────────────
def phase7_naukri(driver):
    agents = CONFIG.get("role_agents", [])
    total = 0
    start = time.time()
    
    naukri_config = CONFIG.get("naukri", {})
    if not naukri_config.get("email"):
        print("  ⏭️  Skipping Naukri: Email missing")
        return 0

    try:
        other_platforms.naukri_login(driver, naukri_config["email"], naukri_config.get("password", ""))
    except Exception as e:
        print(f"  ⏭️  Naukri login failed: {e}")
        return 0

    for i, agent in enumerate(agents, 1):
        elapsed = time.time() - start
        if elapsed >= PHASE_TIMEOUT - 30:
            break

        try:
            count, _ = other_platforms.naukri_apply(
                driver, agent["keywords"], CONFIG["locations"], 10, total, 
                config=CONFIG, dry_run=CONFIG.get("dry_run", False)
            )
            total = count
            print(f"  ✅ Naukri {agent['name']}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ Naukri error: {e}")

    return total


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    CYCLE_DELAY_MINUTES = CONFIG.get("cycle_delay_minutes", 30)

    while True:
        total_start = time.time()

        print("=" * 60)
        print("🤖 JOB AUTO-APPLIER v5 — ALL PHASES (15 min each)")
        print("=" * 60)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"⏰ Total duration for cycle: ~105 minutes (7 phases)")
        print(f"📍 Location: {', '.join(CONFIG['locations'])}")

        agents = CONFIG.get("role_agents", [])
        for a in agents:
            print(f"  {a.get('emoji', '🔹')} {a['name']}: {len(a['keywords'])} keywords")
        print("=" * 60)

        results = {
            "linkedin_applied": 0,
            "jobs_found": 0,
            "web_applied": 0,
            "forms_filled": 0,
            "wellfound_applied": 0,
            "internshala_applied": 0,
            "unstop_applied": 0,
            "naukri_applied": 0,
            "outreach_connects": 0,
            "outreach_messages": 0,
        }

        phases_config = CONFIG.get("phases", {
            "linkedin": {"enabled": True},
            "web_search": {"enabled": True},
            "google_form": {"enabled": True},
            "wellfound": {"enabled": True},
            "internshala": {"enabled": True},
            "unstop": {"enabled": True},
            "naukri": {"enabled": True},
        })

        # ══════════════════════════════════════════
        # PHASE 1: LinkedIn Auto-Apply
        # ══════════════════════════════════════════
        if phases_config.get("linkedin", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 1: LINKEDIN AUTO-APPLY (15 min)")
            print(f"  🧠 AI-powered form filling active")
            print(f"{'═' * 60}")

            try:
                driver1 = create_driver()
                li = CONFIG["linkedin"]
                linkedin_applier.login(driver1, li["email"], li["password"])
                time.sleep(3)
                count = run_with_timeout(phase1_linkedin, (driver1,), PHASE_TIMEOUT, "Phase 1")
                results["linkedin_applied"] = count or 0
                print(f"\n  ✅ Phase 1 done: {results['linkedin_applied']} applications")
            except Exception as e:
                print(f"  ❌ Phase 1 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 1 skipped (Disabled in config)")

        # ══════════════════════════════════════════
        # PHASE 2: Job Finder + Web Search
        # ══════════════════════════════════════════
        if phases_config.get("web_search", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 2: JOB FINDER + WEB SEARCH (15 min)")
            print(f"{'═' * 60}")

            try:
                driver2 = create_driver()
                result2 = run_with_timeout(phase2_jobs, (driver2,), PHASE_TIMEOUT, "Phase 2")
                if result2:
                    results["jobs_found"], results["web_applied"] = result2
                print(f"\n  ✅ Phase 2 done: {results['jobs_found']} found, {results['web_applied']} auto-applied")

                # ══════════════════════════════════════════
                # PHASE 3: Auto-Fill Forms (Conditional within Phase 2)
                # ══════════════════════════════════════════
                if phases_config.get("google_form", {}).get("enabled", True):
                    tabs = len(driver2.window_handles)
                    if tabs > 1:
                        print(f"\n{'═' * 60}")
                        print(f"  📌 PHASE 3: AUTO-FILL FORMS — {tabs} tabs")
                        print(f"{'═' * 60}")
                        filled = run_with_timeout(phase3_fill, (driver2,), PHASE_TIMEOUT, "Phase 3")
                        results["forms_filled"] = filled or 0
                        print(f"\n  ✅ Phase 3 done: {results['forms_filled']} forms filled")
                    else:
                        print(f"\n  ⏭️  Phase 3 skipped — no open tabs to fill")
                else:
                    print(f"\n  ⏭️  Phase 3 skipped (Disabled in config)")
            except Exception as e:
                print(f"  ❌ Phase 2/3 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 2/3 skipped (Disabled in config)")

        # ══════════════════════════════════════════
        # PHASE 4: WELLFOUND
        # ══════════════════════════════════════════
        if phases_config.get("wellfound", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 4: WELLFOUND APP (15 min)")
            print(f"{'═' * 60}")
            try:
                driver3 = create_driver()
                results["wellfound_applied"] = run_with_timeout(phase4_wellfound, (driver3,), PHASE_TIMEOUT, "Phase 4") or 0
                print(f"\n  ✅ Phase 4 done: {results['wellfound_applied']} applications")
            except Exception as e:
                print(f"  ❌ Phase 4 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 4 skipped (Disabled in config)")

        # ══════════════════════════════════════════
        # PHASE 5: INTERNSHALA
        # ══════════════════════════════════════════
        if phases_config.get("internshala", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 5: INTERNSHALA APP (15 min)")
            print(f"{'═' * 60}")
            try:
                driver4 = create_driver()
                results["internshala_applied"] = run_with_timeout(phase5_internshala, (driver4,), PHASE_TIMEOUT, "Phase 5") or 0
                print(f"\n  ✅ Phase 5 done: {results['internshala_applied']} applications")
            except Exception as e:
                print(f"  ❌ Phase 5 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 5 skipped (Disabled in config)")

        # ══════════════════════════════════════════
        # PHASE 6: UNSTOP
        # ══════════════════════════════════════════
        if phases_config.get("unstop", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 6: UNSTOP APP (15 min)")
            print(f"{'═' * 60}")
            try:
                driver5 = create_driver()
                results["unstop_applied"] = run_with_timeout(phase6_unstop, (driver5,), PHASE_TIMEOUT, "Phase 6") or 0
                print(f"\n  ✅ Phase 6 done: {results['unstop_applied']} applications")
            except Exception as e:
                print(f"  ❌ Phase 6 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 6 skipped (Disabled in config)")

        # ══════════════════════════════════════════
        # PHASE 7: NAUKRI
        # ══════════════════════════════════════════
        if phases_config.get("naukri", {}).get("enabled", True):
            print(f"\n{'═' * 60}")
            print(f"  📌 PHASE 7: NAUKRI APP (15 min)")
            print(f"{'═' * 60}")
            try:
                driver6 = create_driver()
                results["naukri_applied"] = run_with_timeout(phase7_naukri, (driver6,), PHASE_TIMEOUT, "Phase 7") or 0
                print(f"\n  ✅ Phase 7 done: {results['naukri_applied']} applications")
            except Exception as e:
                print(f"  ❌ Phase 7 failed: {e}")
        else:
            print(f"\n  ⏭️  Phase 7 skipped (Disabled in config)")

        # FINAL SUMMARY
        # ══════════════════════════════════════════
        total_elapsed = int(time.time() - total_start)
        print(f"\n{'=' * 60}")
        print(f"🎉 ALL PHASES COMPLETE!")
        print(f"{'=' * 60}")
        print(f"📊 LinkedIn auto-applied:   {results['linkedin_applied']}")
        print(f"📑 Jobs found (tabs):       {results['jobs_found']}")
        print(f"🌐 Web search applied:      {results['web_applied']}")
        print(f"📝 Forms auto-filled:       {results['forms_filled']}")
        print(f"🚀 Wellfound applied:       {results['wellfound_applied']}")
        print(f"🎓 Internshala applied:     {results['internshala_applied']}")
        print(f"🎯 Unstop applied:          {results['unstop_applied']}")
        print(f"💼 Naukri applied:          {results['naukri_applied']}")
        print(f"🤝 Outreach connects:       {results['outreach_connects']}")
        print(f"💬 Direct messages:         {results['outreach_messages']}")
        print(f"⏱️  Total time:              {total_elapsed // 60}m {total_elapsed % 60}s")
        print(f"👉 All browsers stay open — review and submit!")
        print(f"{'=' * 60}")

        print(f"\n⏳ Waiting {CYCLE_DELAY_MINUTES} minutes before next cycle...")
        try:
            time.sleep(CYCLE_DELAY_MINUTES * 60)
        except KeyboardInterrupt:
            print("\n🛑 Execution stopped by user.")
            sys.exit(0)
