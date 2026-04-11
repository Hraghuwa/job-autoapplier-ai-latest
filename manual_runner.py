#!/usr/bin/env python3
"""
🚀 UNIFIED MANUAL RUNNER — Job Auto-Applier
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run any phase manually from your terminal.

Phases:
1: LinkedIn (AI Auto-Apply)
2: Internshala (Auto-Apply)
3: Wellfound (Auto-Apply)
4: Naukri (Auto-Apply)
5: Unstop (Auto-Apply)
6: Web Discovery & ATS Apply
7: Smart Form Fill (Remaining Tabs)

Usage:
  python manual_runner.py --phase 1      (Run only LinkedIn)
  python manual_runner.py --all          (Run all phases sequentially)
  python manual_runner.py --headless     (Run in background)
  python manual_runner.py --list         (Show all phases)
"""

import argparse
import time
import sys
import os
import traceback
from datetime import datetime

# Import local modules
from config import CONFIG
import linkedin_applier
import internshala_applier
import wellfound_applier
import other_platforms
import web_search_applier
import google_form_filler

# Minimal imports from main/orchestrator
try:
    from main import create_driver, safe_quit, load_tracker, save_tracker, add_applied_urls, get_applied_urls
except ImportError:
    # Fallback if main.py is moved/modified
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import json

    def create_driver(headless=False):
        opts = Options()
        if headless: opts.add_argument("--headless=new")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def safe_quit(driver):
        print("  🌐 Browser persistence active (tabs left open).")
        pass

    def load_tracker():
        if os.path.exists("applied_jobs.json"):
            with open("applied_jobs.json") as f: return json.load(f)
        return {"applied_urls": []}

    def save_tracker(tracker):
        with open("applied_jobs.json", "w") as f: json.dump(tracker, f, indent=2)

    def get_applied_urls(tracker): return set(tracker.get("applied_urls", []))
    def add_applied_urls(tracker, new_urls):
        existing = set(tracker.get("applied_urls", []))
        for u in new_urls: tracker.setdefault("applied_urls", []).append(u)
        save_tracker(tracker)

# ─────────────────────────────────────────────
#  PHASE RUNNERS
# ─────────────────────────────────────────────

def run_phase1_linkedin(driver, args):
    print("\n[Phase 1] 🤖 LinkedIn AI Auto-Apply")
    agents = CONFIG.get("role_agents", [])
    total = 0
    tracker = load_tracker()
    for i, agent in enumerate(agents, 1):
        print(f"  [{i}/{len(agents)}] Agent: {agent['name']}")
        cfg = dict(CONFIG); cfg["keywords"] = agent["keywords"]
        try:
            count = linkedin_applier.run(driver, cfg, 0, CONFIG["max_jobs_per_day"], get_applied_urls(tracker))
            total += count
        except Exception as e:
            print(f"  ⚠️  LinkedIn Agent Error: {e}")
    print(f"✅ Phase 1 Complete: {total} applications")
    return total

def run_phase2_internshala(driver, args):
    print("\n[Phase 2] 🎓 Internshala Auto-Apply")
    ish_config = CONFIG.get("internshala", {})
    if not ish_config.get("email"): 
        print("  ❌ Skipping: No Internshala credentials in config.py")
        return 0
    try:
        internshala_applier.login(driver, ish_config["email"], ish_config["password"])
        count = internshala_applier.run(driver, CONFIG, 0, 10, get_applied_urls(load_tracker()))
        print(f"✅ Phase 2 Complete: {count} applications")
        return count
    except Exception as e:
        print(f"  ❌ Internshala Error: {e}")
        return 0

def run_phase3_wellfound(driver, args):
    print("\n[Phase 3] 🚀 Wellfound Auto-Apply")
    wf_config = CONFIG.get("wellfound", {})
    if not wf_config.get("email"):
        print("  ❌ Skipping: No Wellfound credentials in config.py")
        return 0
    try:
        wellfound_applier.login(driver, wf_config["email"], wf_config["password"])
        count, new_urls = wellfound_applier.search_and_apply(driver, CONFIG["keywords"], CONFIG["locations"], 10, 0, CONFIG, get_applied_urls(load_tracker()))
        if new_urls: add_applied_urls(load_tracker(), new_urls)
        print(f"✅ Phase 3 Complete: {count} applications")
        return count
    except Exception as e:
        print(f"  ❌ Wellfound Error: {e}")
        return 0

def run_phase4_naukri(driver, args):
    print("\n[Phase 4] 💼 Naukri Auto-Apply")
    naukri_config = CONFIG.get("naukri", {})
    if not naukri_config.get("email"):
        print("  ❌ Skipping: No Naukri credentials in config.py")
        return 0
    try:
        other_platforms.naukri_login(driver, naukri_config["email"], naukri_config.get("password", ""))
        count, _ = other_platforms.naukri_apply(driver, CONFIG.get("keywords", []), CONFIG["locations"], 10, 0, config=CONFIG)
        print(f"✅ Phase 4 Complete: {count} applications")
        return count
    except Exception as e:
        print(f"  ❌ Naukri Error: {e}")
        return 0

def run_phase5_unstop(driver, args):
    print("\n[Phase 5] 🎯 Unstop Auto-Apply")
    unstop_config = CONFIG.get("unstop", {})
    if not unstop_config.get("email"):
        print("  ❌ Skipping: No Unstop credentials in config.py")
        return 0
    try:
        other_platforms.unstop_login(driver, unstop_config["email"], unstop_config.get("password", ""))
        count, _ = other_platforms.unstop_apply(driver, CONFIG.get("keywords", []), CONFIG["locations"], 10, 0, config=CONFIG)
        print(f"✅ Phase 5 Complete: {count} applications")
        return count
    except Exception as e:
        print(f"  ❌ Unstop Error: {e}")
        return 0

def run_phase6_web(driver, args):
    print("\n[Phase 6] 🌐 Unified Web Discovery & ATS Apply")
    try:
        applied_count, urls = web_search_applier.search_and_apply(driver, CONFIG, get_applied_urls(load_tracker()))
        if urls: add_applied_urls(load_tracker(), urls)
        print(f"✅ Phase 6 Complete: {applied_count} applications | {len(urls)} jobs found")
        return applied_count
    except Exception as e:
        print(f"  ❌ Web Search Error: {e}")
        return 0

def run_phase7_fill(driver, args):
    print("\n[Phase 7] 📝 Smart Form Fill (All Open Tabs)")
    try:
        filled, fields = google_form_filler.auto_fill_open_tabs(driver, CONFIG)
        print(f"✅ Phase 7 Complete: Filled {fields} fields across {filled} tabs")
        return filled
    except Exception as e:
        print(f"  ❌ Form Fill Error: {e}")
        return 0

# ─────────────────────────────────────────────
#  PHASE MAPPING
# ─────────────────────────────────────────────
PHASE_MAP = {
    1: ("LinkedIn", run_phase1_linkedin),
    2: ("Internshala", run_phase2_internshala),
    3: ("Wellfound", run_phase3_wellfound),
    4: ("Naukri", run_phase4_naukri),
    5: ("Unstop", run_phase5_unstop),
    6: ("Web Discovery", run_phase6_web),
    7: ("Form Fill", run_phase7_fill),
}

# ─────────────────────────────────────────────
#  MAIN CLI
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="🚀 Job Auto-Applier Manual Runner")
    parser.add_argument("--phase", type=int, help="Phase number to run (1-7)")
    parser.add_argument("--all", action="store_true", help="Run ALL phases sequentially")
    parser.add_argument("--headless", action="store_true", help="Run browser in background")
    parser.add_argument("--list", action="store_true", help="List all phases")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable Phases:")
        for n, (name, _) in PHASE_MAP.items():
            print(f"  Phase {n}: {name}")
        return

    selected_phases = []
    if args.all:
        selected_phases = sorted(PHASE_MAP.keys())
    elif args.phase:
        if args.phase in PHASE_MAP:
            selected_phases = [args.phase]
        else:
            print(f"❌ Invalid phase: {args.phase}. Choose 1-7 or use --list.")
            return
    else:
        parser.print_help()
        return

    print("=" * 60)
    print("🤖 JOB AUTO-APPLIER — MANUAL RUNNER")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"🎯 Running: {', '.join([PHASE_MAP[p][0] for p in selected_phases])}")
    print("=" * 60)

    driver = None
    try:
        driver = create_driver(headless=args.headless)
        for p_num in selected_phases:
            name, func = PHASE_MAP[p_num]
            try:
                func(driver, args)
            except Exception:
                print(f"  ❌ ERROR in {name}:")
                traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("✅ MANUAL RUN COMPLETE")
        print("👉 The browser will remain open so you can review filled forms/tabs.")
        print("=" * 60)
        
        # Keep process alive so browser stays open if safe_quit doesn't quit
        while len(driver.window_handles) > 0:
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        traceback.print_exc()
    finally:
        if driver:
            # We don't quit by default to let user review, but if it failed early we might want to
            pass

if __name__ == "__main__":
    main()
