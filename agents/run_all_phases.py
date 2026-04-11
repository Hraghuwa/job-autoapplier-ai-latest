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

PHASE_TIMEOUT = 15 * 60  # 15 minutes per phase


# ─────────────────────────────────────────────
#  BROWSER SETUP
# ─────────────────────────────────────────────
def create_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-notifications")
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

        if isinstance(agent, str):
            print(f"\n  {'▓' * 55}")
            print(f"  🔹 AGENT {i}/{len(agents)}: {agent}")
            print(f"  ⏰ {remaining // 60}m {remaining % 60}s left")
            print(f"  {'▓' * 55}")
            keywords = [agent]
            agent_name = agent
        else:
            print(f"\n  {'▓' * 55}")
            print(f"  {agent.get('emoji', '🔹')} AGENT {i}/{len(agents)}: {agent['name']}")
            print(f"  📋 {', '.join(agent['keywords'])}")
            print(f"  ⏰ {remaining // 60}m {remaining % 60}s left")
            print(f"  {'▓' * 55}")
            keywords = agent["keywords"]
            agent_name = agent["name"]

        cfg = dict(CONFIG)
        cfg["keywords"] = keywords

        try:
            count = linkedin_applier.run(
                driver, cfg, 0, CONFIG["max_jobs_per_day"], applied_urls=set()
            )
            total += count
            print(f"  ✅ {agent_name}: {count} jobs applied")
        except Exception as e:
            print(f"  ❌ {agent_name} error: {str(e)[:50]}")

    return total


# ─────────────────────────────────────────────
#  PHASE 2: Job Finder + Web Search Applier
# ─────────────────────────────────────────────
def phase2_jobs(driver):
    """Search for jobs and auto-apply via web search."""
    start = time.time()

    # 2A: Job Finder — open tabs (first 7 min)
    print("\n  📑 Phase 2A: Job Finder — opening tabs...")
    found_urls = []
    try:
        found_urls = job_finder.find_all_jobs(driver, CONFIG, set())
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
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    CYCLE_DELAY_MINUTES = 30  # Delay between full complete cycles

    while True:
        total_start = time.time()

        print("=" * 60)
        print("🤖 JOB AUTO-APPLIER v4 — ALL PHASES (15 min each)")
        print("=" * 60)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"⏰ Total runtime: ~60 minutes")
        print(f"📍 Location: {', '.join(CONFIG['locations'])}")

        agents = CONFIG.get("role_agents", [])
        for a in agents:
            if isinstance(a, str):
                print(f"  🔹 {a}")
            else:
                print(f"  {a.get('emoji', '🔹')} {a['name']}: {len(a['keywords'])} keywords")
        print("=" * 60)

        results = {
            "linkedin_applied": 0,
            "jobs_found": 0,
            "web_applied": 0,
            "forms_filled": 0,
            "outreach_connects": 0,
            "outreach_messages": 0,
        }

        # ══════════════════════════════════════════
        # PHASE 1: LinkedIn Auto-Apply (15 min)
        # ══════════════════════════════════════════
        print(f"\n{'═' * 60}")
        print(f"  📌 PHASE 1: LINKEDIN AUTO-APPLY (15 min)")
        print(f"  🧠 AI-powered form filling active")
        print(f"{'═' * 60}")

        driver1 = create_driver()
        print("  🌐 Browser started")
        print("  🔐 Logging into LinkedIn...")

        li = CONFIG["linkedin"]
        linkedin_applier.login(driver1, li["email"], li["password"])
        time.sleep(3)

        count = run_with_timeout(phase1_linkedin, (driver1,), PHASE_TIMEOUT, "Phase 1")
        results["linkedin_applied"] = count or 0
        print(f"\n  ✅ Phase 1 done: {results['linkedin_applied']} applications")
        print(f"  👉 Browser stays open")

        # ══════════════════════════════════════════
        # PHASE 2: Job Finder + Web Search (15 min)
        # ══════════════════════════════════════════
        print(f"\n{'═' * 60}")
        print(f"  📌 PHASE 2: JOB FINDER + WEB SEARCH (15 min)")
        print(f"{'═' * 60}")

        driver2 = create_driver()
        print("  🌐 Browser started")

        result2 = run_with_timeout(phase2_jobs, (driver2,), PHASE_TIMEOUT, "Phase 2")
        if result2:
            results["jobs_found"], results["web_applied"] = result2
        print(f"\n  ✅ Phase 2 done: {results['jobs_found']} found, {results['web_applied']} auto-applied")

        # ══════════════════════════════════════════
        # PHASE 3: Auto-Fill Forms (15 min)
        # ══════════════════════════════════════════
        try:
            if job_finder.is_driver_alive(driver2):
                tabs = len(driver2.window_handles)
                if tabs > 1:
                    print(f"\n{'═' * 60}")
                    print(f"  📌 PHASE 3: AUTO-FILL FORMS (15 min) — {tabs} tabs")
                    print(f"{'═' * 60}")

                    filled = run_with_timeout(phase3_fill, (driver2,), PHASE_TIMEOUT, "Phase 3")
                    results["forms_filled"] = filled or 0
                    print(f"\n  ✅ Phase 3 done: {results['forms_filled']} forms filled")
                else:
                    print(f"\n  ⏭️  Phase 3 skipped — no open tabs to fill")
        except Exception:
            print(f"  ⏭️  Phase 3 skipped — browser not available")

        print(f"  👉 Both browsers stay open — review and submit!")

        # ══════════════════════════════════════════
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
