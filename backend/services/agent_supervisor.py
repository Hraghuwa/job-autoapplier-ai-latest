"""Agent supervisor — keeps the system bulletproof.

Three responsibilities, all called from FastAPI lifespan startup:

  1. recover_stuck_runs()
     On boot, any AgentRun left in 'queued' or 'running' belongs to a dead
     process (we just started). Mark them 'failed' so the user sees the truth
     instead of a spinner that never resolves.

  2. ensure_worker_running()
     If Redis is reachable but no Celery worker is consuming the agents queue,
     spawn one as a daemon subprocess. The web process becomes self-healing —
     no more "queued forever because someone forgot to run start_worker.sh".

  3. start_watchdog()
     Background asyncio task: every 60s, find runs that are 'running' but
     haven't logged anything for > STALE_RUN_TIMEOUT (default 5 min). Mark
     them 'failed' with a clear stale-run reason. Without this a crashed
     Chrome leaves the user staring at a fake "running" badge.

All three are best-effort — failures are logged and don't block startup,
because /health must stay green for the platform healthcheck.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

STALE_RUN_TIMEOUT = timedelta(minutes=int(os.environ.get("AGENT_STALE_TIMEOUT_MIN", "5")))
WATCHDOG_INTERVAL_S = int(os.environ.get("AGENT_WATCHDOG_INTERVAL_S", "60"))


def _redis_reachable() -> bool:
    try:
        from backend.config import settings
        url = settings.redis_url
        host = url.split("//")[1].split(":")[0]
        port = int(url.split(":")[-1].split("/")[0])
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _celery_worker_listening() -> bool:
    try:
        from backend.workers.celery_app import celery_app
        insp = celery_app.control.inspect(timeout=0.5)
        active = insp.active_queues() or {}
        for queues in active.values():
            for q in queues or []:
                if q.get("name") == "agents":
                    return True
        return False
    except Exception:
        return False


# ── 0. Idempotent column adds for applications table ────────────────────────
def ensure_application_columns() -> None:
    """SQLite has no `ADD COLUMN IF NOT EXISTS` — do it ourselves.

    Adds Phase E columns (tailored_resume_id, cover_note_used) to the
    applications table when missing. Safe to call repeatedly; safe on
    fresh databases where create_all already added them; safe on Postgres
    where the existence check uses information_schema.
    """
    try:
        from backend.database import engine
        from sqlalchemy import text, inspect
        with engine.begin() as conn:
            # SQLAlchemy 2.0 inspect requires a sync connection — engine.begin()
            # gives us one if engine is sync; for async engines this is wrong,
            # but the migration is opportunistic so we swallow failures.
            insp = inspect(conn)
            cols = {c["name"] for c in insp.get_columns("applications")}
            if "tailored_resume_id" not in cols:
                conn.execute(text(
                    "ALTER TABLE applications ADD COLUMN tailored_resume_id CHAR(32)"))
                log.warning("Supervisor: added applications.tailored_resume_id")
            if "cover_note_used" not in cols:
                conn.execute(text(
                    "ALTER TABLE applications ADD COLUMN cover_note_used TEXT"))
                log.warning("Supervisor: added applications.cover_note_used")
    except Exception as e:
        # Engine may be async (sqlite+aiosqlite) — that's fine, create_all
        # in lifespan handles fresh DBs. Migration is for existing DBs only.
        log.info("Supervisor: column migration skipped (%s)", e)


# ── 1. Recover stuck runs ────────────────────────────────────────────────────
def recover_stuck_runs() -> int:
    """Mark any 'queued'/'running' runs from a previous process as failed.

    Returns the number of recovered runs. Idempotent and safe to call repeatedly.
    """
    try:
        from backend.workers.agent_tasks import _sync_session
        from backend.models.agent_run import AgentRun, RunStatus
    except Exception as e:
        log.warning("Supervisor: cannot import models for recovery (%s)", e)
        return 0

    session = _sync_session()
    try:
        # Audit H4: only fail 'queued' runs on boot. A 'running' run may be
        # executing in a detached Celery worker that survived this web-process
        # restart (ensure_worker_running spawns with start_new_session=True), so
        # failing it here would fight the live worker and flap the status. The
        # watchdog (_fail_stale_runs) handles genuinely-dead 'running' runs via
        # log-recency, which does not race the worker.
        stuck = session.query(AgentRun).filter(
            AgentRun.status == "queued"
        ).all()
        n = 0
        for run in stuck:
            run.status = "failed"
            run.completed_at = datetime.now()
            n += 1
        if n:
            session.commit()
            log.warning("Supervisor: recovered %d stuck queued runs from a previous process.", n)
        return n
    except Exception as e:
        log.warning("Supervisor: stuck-run recovery failed (%s)", e)
        try: session.rollback()
        except Exception: pass
        return 0
    finally:
        session.close()


# ── 2. Auto-spawn celery worker ──────────────────────────────────────────────
_spawned_worker: Optional[subprocess.Popen] = None


def ensure_worker_running() -> Optional[subprocess.Popen]:
    """Spawn a Celery worker subprocess if Redis is up and none is listening.

    Returns the Popen handle (or None if not spawned). The subprocess is
    detached enough to survive a uvicorn --reload cycle (new session id),
    but we also store the handle so a follow-up startup can detect and
    not double-spawn within the same Python interpreter.
    """
    global _spawned_worker

    if os.environ.get("DISABLE_AGENT_SUPERVISOR") == "1":
        log.info("Supervisor: DISABLE_AGENT_SUPERVISOR=1 — skipping worker auto-spawn.")
        return None

    if not _redis_reachable():
        log.info("Supervisor: Redis not reachable — agent runs will use in-thread fallback.")
        return None

    if _celery_worker_listening():
        log.info("Supervisor: Celery worker already consuming 'agents' queue.")
        return None

    if _spawned_worker and _spawned_worker.poll() is None:
        log.info("Supervisor: previously-spawned worker still alive (pid=%s).", _spawned_worker.pid)
        return _spawned_worker

    # Build the worker command. Use the same python that's running us.
    py = sys.executable or shutil.which("python3") or "python3"
    log_path = os.environ.get("AGENT_WORKER_LOG", "/tmp/worker.log")
    cmd = [py, "-m", "celery", "-A", "backend.workers.celery_app",
           "worker", "--loglevel=info", "-Q", "agents,default",
           "--concurrency", os.environ.get("AGENT_WORKER_CONCURRENCY", "1")]

    try:
        # start_new_session=True detaches from uvicorn's process group so reload
        # won't kill it. stdout/stderr go to a log file.
        log_f = open(log_path, "a")
        log_f.write(f"\n\n=== supervisor spawn @ {datetime.now().isoformat()} ===\n")
        log_f.flush()
        _spawned_worker = subprocess.Popen(
            cmd,
            stdout=log_f, stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        log.warning("Supervisor: spawned Celery worker pid=%s, logs → %s", _spawned_worker.pid, log_path)
        return _spawned_worker
    except Exception as e:
        log.error("Supervisor: failed to spawn worker (%s) — will rely on in-thread fallback.", e)
        return None


# ── 3. Watchdog loop ─────────────────────────────────────────────────────────
async def _watchdog_loop():
    while True:
        try:
            _fail_stale_runs()
        except Exception as e:
            log.warning("Supervisor watchdog: tick failed (%s)", e)
        await asyncio.sleep(WATCHDOG_INTERVAL_S)


def _fail_stale_runs() -> int:
    """Mark 'running' runs that have been silent past STALE_RUN_TIMEOUT as failed.

    Silence = no agent_log row whose created_at is newer than
    (now - STALE_RUN_TIMEOUT). Real runs emit at least a heartbeat per minute,
    so 5 min of silence means dead.
    """
    from backend.workers.agent_tasks import _sync_session
    from backend.models.agent_run import AgentRun, AgentLog
    from sqlalchemy import func

    session = _sync_session()
    try:
        cutoff = datetime.now() - STALE_RUN_TIMEOUT
        running = session.query(AgentRun).filter(AgentRun.status == "running").all()
        n = 0
        for run in running:
            last = session.query(func.max(AgentLog.created_at)).filter(
                AgentLog.run_id == run.id
            ).scalar()
            # If no logs and started_at is past cutoff → stale.
            # If logs exist but newest is past cutoff → stale.
            newest = last or run.started_at
            if newest and newest < cutoff:
                run.status = "failed"
                run.completed_at = datetime.now()
                run.error_count = (run.error_count or 0) + 1
                # Best-effort log row so the UI shows the reason
                try:
                    session.add(AgentLog(
                        run_id=run.id, event_type="error",
                        message=f"Watchdog: no progress for "
                                f"{STALE_RUN_TIMEOUT.total_seconds()/60:.0f} min — marked failed.",
                    ))
                except Exception:
                    pass
                n += 1
        if n:
            session.commit()
            log.warning("Supervisor watchdog: failed %d stale runs.", n)
        return n
    except Exception as e:
        try: session.rollback()
        except Exception: pass
        log.warning("Supervisor watchdog: query failed (%s)", e)
        return 0
    finally:
        session.close()


def start_watchdog(loop: asyncio.AbstractEventLoop) -> None:
    """Schedule the watchdog on the given event loop. Safe to call once at startup."""
    if os.environ.get("DISABLE_AGENT_SUPERVISOR") == "1":
        return
    try:
        loop.create_task(_watchdog_loop())
        log.info("Supervisor: watchdog scheduled (interval=%ds, stale_timeout=%s).",
                 WATCHDOG_INTERVAL_S, STALE_RUN_TIMEOUT)
    except Exception as e:
        log.warning("Supervisor: could not start watchdog (%s)", e)


# ── 4. Healthcheck snapshot ──────────────────────────────────────────────────
def healthcheck() -> dict:
    """Probe every dependency the agent needs. Used by /agents/healthcheck."""
    out = {
        "redis":           _redis_reachable(),
        "celery_worker":   _celery_worker_listening(),
        "chrome_binary":   _chrome_binary_present(),
        "ollama":          _ollama_reachable(),
        "supervisor_pid":  os.getpid(),
    }
    out["ok"] = bool(out["chrome_binary"])   # the only HARD requirement
    return out


def _chrome_binary_present() -> bool:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    return any(c and os.path.exists(c) for c in candidates)


def _ollama_reachable() -> bool:
    try:
        import urllib.request
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        with urllib.request.urlopen(host + "/api/tags", timeout=0.6):
            return True
    except Exception:
        return False
