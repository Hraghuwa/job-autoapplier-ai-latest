"""Run a single agent phase in an isolated subprocess (audit C2).

Invoked by backend.workers.agent_tasks._execute_subprocess as:

    python agents/run_phase_subprocess.py <config_json> <phase> <run_id> <result_json>

Why a subprocess: the appliers read a module-global `config.CONFIG`, print
progress to stdout, and were previously multiplexed in the worker behind one
process-global lock + a global stdout swap — capping the whole platform to one
run at a time. Running each phase as its own interpreter gives full isolation:
its own CONFIG, its own stdout (the parent reads it via a pipe), no shared lock.

This script owns the non-serializable parts of the config that cannot cross the
process boundary as JSON:
  * the sync DB session factory (rebuilt from DATABASE_URL),
  * the LinkedIn cookie refresh-back callback (a direct DB write),
  * the stop signal (a threading.Event fed by polling Redis `pause:{run_id}`).

It prints exactly what the appliers print; the parent classifies those lines.
On exit it writes {"applied": <int>} to the result file.
"""
import json
import os
import sys
import threading
import time
import traceback


def _setup_path():
    here = os.path.dirname(os.path.abspath(__file__))          # .../agents
    repo_root = os.path.abspath(os.path.join(here, ".."))
    # agents dir first so `import config` resolves to agents/config.py (NOT the
    # repo-root config.py), then repo_root so `import backend.*` works.
    if here not in sys.path:
        sys.path.insert(0, here)
    if repo_root not in sys.path:
        sys.path.insert(1, repo_root)
    return repo_root


def _start_stop_poller(run_id: str, stop_event: threading.Event):
    """Set stop_event when Redis pause:{run_id} appears. Daemon thread."""
    def _poll():
        while not stop_event.is_set():
            try:
                import redis as _r
                from backend.config import settings as _s
                c = _r.from_url(_s.redis_url, decode_responses=True,
                                socket_connect_timeout=0.3)
                if c.get(f"pause:{run_id}") == "1":
                    stop_event.set()
                    return
            except Exception:
                pass
            time.sleep(2)
    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    return t


def _build_session_factory(repo_root: str):
    from backend.config import settings
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    url = settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    eng = create_engine(url, future=True,
                        connect_args={"check_same_thread": False} if "sqlite" in url else {})
    return sessionmaker(eng, expire_on_commit=False)


def _make_cookie_saver(user_id: str):
    def _save(fresh_json: str):
        try:
            import uuid as _uuid
            from backend.models.profile import UserProfile
            from sqlalchemy.orm.attributes import flag_modified
            from backend.services.crypto_service import encrypt
            from backend.workers.agent_tasks import _sync_session
            s = _sync_session()
            try:
                prof = s.query(UserProfile).filter_by(user_id=_uuid.UUID(user_id)).first()
                if prof:
                    creds = dict(prof.platform_passwords or {})
                    creds["linkedin_cookies"] = encrypt(fresh_json)
                    prof.platform_passwords = creds
                    flag_modified(prof, "platform_passwords")
                    s.commit()
            finally:
                s.close()
        except Exception as e:
            print(f"  ⚠️  Could not refresh LinkedIn cookies: {e}")
    return _save


def _dispatch(phase: int) -> int:
    if phase == 1:
        from run_phase1 import main as fn
        return fn() or 0
    if phase == 2:
        from orchestrator import run_internshala_phase as fn
    elif phase == 3:
        from orchestrator import run_wellfound_phase as fn
    elif phase == 4:
        from orchestrator import run_naukri_phase as fn
    elif phase == 5:
        from orchestrator import run_unstop_phase as fn
    elif phase == 6:
        from orchestrator import run_web_search_phase as fn
    elif phase == 7:
        from orchestrator import run_form_fill_phase as fn
    else:
        return 0
    return fn() or 0


def _persist_autofill_bank(user_id: str, config_mod):
    try:
        bank = config_mod.CONFIG.get("autofill_bank", {})
        if not bank:
            return
        import uuid as _uuid
        from backend.models.profile import UserProfile
        from backend.workers.agent_tasks import _sync_session
        s = _sync_session()
        try:
            prof = s.query(UserProfile).filter_by(user_id=_uuid.UUID(user_id)).first()
            if prof:
                existing = prof.autofill_bank or {}
                existing.update(bank)
                prof.autofill_bank = existing
                s.commit()
        finally:
            s.close()
    except Exception as e:
        print(f"  ⚠️  Could not persist autofill bank: {e}")


def main(argv):
    if len(argv) < 5:
        print("usage: run_phase_subprocess.py <config_json> <phase> <run_id> <result_json>")
        return 2
    cfg_path, phase_s, run_id, res_path = argv[1], argv[2], argv[3], argv[4]
    phase = int(phase_s)
    repo_root = _setup_path()

    applied = 0
    try:
        with open(cfg_path) as f:
            config = json.load(f)

        # Re-attach the non-serializable bits this process owns.
        config["_server_mode"] = True
        config["current_run_id"] = run_id
        config["run_id"] = run_id
        config["chrome_profile_suffix"] = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in str(config.get("user_id", "")))

        stop_event = threading.Event()
        _start_stop_poller(run_id, stop_event)
        config["_stop_event"] = stop_event

        try:
            config["_session_factory"] = _build_session_factory(repo_root)
            config["_tailored_upload_dir"] = os.environ.get(
                "TAILORED_UPLOAD_DIR", os.path.join(repo_root, "uploads", "tailored"))
        except Exception as e:
            print(f"  ⚠️  Could not build session factory: {e}")

        config["_save_linkedin_cookies"] = _make_cookie_saver(str(config.get("user_id", "")))

        import config as config_mod  # agents/config.py
        for k, v in config.items():
            setattr(config_mod, k, v)
        config_mod.CONFIG.clear()
        config_mod.CONFIG.update(config)

        applied = _dispatch(phase) or 0
        if phase == 7:
            _persist_autofill_bank(str(config.get("user_id", "")), config_mod)

    except Exception as e:
        print(f"❌ Phase {phase} subprocess error: {e}")
        traceback.print_exc()
    finally:
        try:
            with open(res_path, "w") as f:
                json.dump({"applied": int(applied or 0)}, f)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
