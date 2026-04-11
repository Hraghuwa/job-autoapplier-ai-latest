import time
from datetime import datetime
from config import CONFIG
from main import create_driver, safe_quit, load_tracker, save_tracker, get_applied_urls, run_linkedin_agent
import linkedin_applier


def main():
    agents = CONFIG.get("role_agents", [])

    print("=" * 60)
    print("🤖 JOB AUTO-APPLIER - RUNNING ONLY PHASE 1 (LinkedIn)")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n📌 PHASE 1: LinkedIn Auto-Apply (AI form filling)")
    print(f"   {len(agents)} role agents with Gemini AI")
    for a in agents:
        if isinstance(a, str):
            print(f"     🔹 {a}")
        else:
            print(f"     {a.get('emoji', '🔹')} {a['name']}")

    tracker = load_tracker()
    print(f"\n📊 Previously applied: {len(get_applied_urls(tracker))} unique URLs\n")

    total_applied = 0

    print(f"\n{'═' * 60}")
    print(f"  📌 PHASE 1: LINKEDIN AUTO-APPLY")
    print(f"{'═' * 60}")

    linkedin_pwd = CONFIG["linkedin"]["password"]
    if not linkedin_pwd or linkedin_pwd.startswith("YOUR_"):
        print("  [LinkedIn] ❌ Password not set. Update config.py.")
        return

    # Create ONE browser session and login ONCE — shared across all agents
    driver = create_driver(headless=CONFIG.get("headless", False))
    print(f"  [LinkedIn] 🔐 Logging in (once for all agents)...")
    login_ok = linkedin_applier.login(driver, CONFIG["linkedin"]["email"], linkedin_pwd)

    if not login_ok:
        print("  [LinkedIn] ❌ Login failed. Exiting.")
        safe_quit(driver)
        return

    print("  [LinkedIn] ✅ Logged in. Starting agents...\n")

    _stop = CONFIG.get("_stop_event")
    try:
        for i, agent in enumerate(agents, 1):
            if _stop and _stop.is_set():
                print("  [Phase 1] 🛑 Stop requested — exiting agent loop.")
                break
            count = run_linkedin_agent(agent, i, len(agents), tracker, shared_driver=driver)
            total_applied += count
            if i < len(agents):
                if _stop and _stop.is_set():
                    break
                print(f"\n  ⏳ Next agent in 5s...")
                time.sleep(5)
    finally:
        _stop = CONFIG.get("_stop_event")
        if _stop and _stop.is_set():
            print("  [Phase 1] ⏸️  Stopped by user — browser tab preserved for inspection.")
            # Do NOT quit driver — leave the browser open so user can see where it stopped
        else:
            safe_quit(driver)

    print(f"\n  ✅ PHASE 1 COMPLETE: {total_applied} LinkedIn applications")

    tracker["total"] = tracker.get("total", 0) + total_applied
    tracker["cycles"] = tracker.get("cycles", 0) + 1
    tracker["last_run"] = datetime.now().isoformat()
    save_tracker(tracker)

    print(f"\n{'=' * 60}")
    print(f"✅ ALL DONE! (Phase 1 Only)")
    print(f"📊 LinkedIn auto-applied: {total_applied}")
    print(f"📊 Total tracked URLs: {len(get_applied_urls(tracker))}")
    print(f"{'=' * 60}")

    return total_applied


if __name__ == "__main__":
    main()
