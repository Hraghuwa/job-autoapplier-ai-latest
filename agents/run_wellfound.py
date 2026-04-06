"""
🚀 Wellfound Auto-Applier — Standalone Runner
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Logs into Wellfound, searches for intern jobs, and auto-applies.
"""

import time
import traceback
from datetime import datetime

from config import CONFIG
import wellfound_applier

# Reuse main.py utilities
from main import (
    load_tracker, save_tracker, get_applied_urls,
    add_applied_urls, create_driver, safe_quit
)


def main():
    print("=" * 60)
    print("🚀 WELLFOUND AUTO-APPLIER")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"📍 Location: {', '.join(CONFIG['locations'])}")
    print(f"📄 Resume: {CONFIG['resume_path'].split('/')[-1]}")
    print(f"🔑 Keywords: {len(CONFIG['keywords'])} roles")
    print("=" * 60)

    tracker = load_tracker()
    applied_urls = get_applied_urls(tracker)
    print(f"\n📊 Previously applied: {len(applied_urls)} unique URLs\n")

    # Wellfound credentials
    wf_config = CONFIG.get("wellfound", {})
    email = wf_config.get("email", "")
    password = wf_config.get("password", "")

    if not email or not password or password.startswith("YOUR_"):
        print("❌ Wellfound credentials not set in config.py!")
        return

    driver = None
    applied = 0

    try:
        driver = create_driver(headless=False)
        print("🌐 Browser started\n")

        # Login
        login_ok = wellfound_applier.login(driver, email, password)
        if not login_ok:
            print("❌ Login failed. Exiting.")
            safe_quit(driver)
            return

        # Search and apply
        applied, new_urls = wellfound_applier.search_and_apply(
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

        # Update tracker
        tracker["cycles"] = tracker.get("cycles", 0) + 1
        tracker["last_run"] = datetime.now().isoformat()
        save_tracker(tracker)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
    finally:
        if driver:
            safe_quit(driver)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✅ WELLFOUND SESSION COMPLETE!")
    print(f"{'─' * 60}")
    print(f"  📊 Applied: {applied} jobs")
    print(f"  📊 All-time URLs: {len(get_applied_urls(tracker))}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
