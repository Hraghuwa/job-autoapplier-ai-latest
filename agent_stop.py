"""Lightweight bridge for CLI agents to honour the web-backend's Pause button.

Usage in any agent loop:
    from agent_stop import should_stop
    if should_stop():
        print("  ⏹  Stop requested — exiting agent early.")
        break
"""


def should_stop() -> bool:
    """Check the backend's stop event for the current run. Safe to call
    in both web (threaded bridge) and CLI contexts — returns False if
    no run_id is set or the backend module isn't importable.
    """
    try:
        from config import CONFIG
        run_id = CONFIG.get("current_run_id")
        if not run_id:
            return False
        from backend.workers.agent_tasks import is_stopping
        return is_stopping(run_id)
    except Exception:
        return False
