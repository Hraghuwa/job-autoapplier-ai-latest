"""Platform automation fixes: scheduler, LinkedIn cookies/caps, structured job
records, prepared counts, Stop without Redis, watchdog heartbeat, JD cache, AI
metering, shared caps, per-user tracker, persisted story bank."""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.database import Base
from backend.models.agent_run import AgentRun, RunStatus
from backend.models.application import Application, ApplicationStatus
from backend.models.profile import UserProfile
from backend.models.resume import AIRequest
from backend.models.user import User
from backend.workers import agent_tasks

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENTS = os.path.join(ROOT, "agents")
sys.path.insert(0, AGENTS)


def _agent_mod(name):
    """The agents/ module, never the drifted repo-root copy of the same name
    (main.py, linkedin_applier.py, config.py exist in both places)."""
    import importlib
    if sys.path[0] != AGENTS:
        sys.path.insert(0, AGENTS)
    m = sys.modules.get(name)
    if m is None or os.path.dirname(os.path.abspath(getattr(m, "__file__", "") or "")) != AGENTS:
        sys.modules.pop(name, None)
        m = importlib.import_module(name)
    return m


@pytest.fixture()
def db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(eng)
    S = sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(agent_tasks, "_sync_session", lambda: S())
    with S() as s:
        u = User(email="u@example.com", hashed_password="x", name="U", plan="pro")
        s.add(u)
        s.commit()
        uid = u.id
    return S, uid


# ── Scheduler ────────────────────────────────────────────────────────────────

def test_scheduler_enqueues_due_phase_once(db, monkeypatch):
    S, uid = db
    with S() as s:
        s.add(UserProfile(user_id=uid, job_preferences={
            "schedule": {"enabled": True, "cron": "* * * * *", "phases": [6]}}))
        s.commit()
    sent = []
    monkeypatch.setattr(agent_tasks.run_phase_task, "apply_async",
                        lambda args, queue: sent.append((args, queue)))
    agent_tasks.check_schedules()
    agent_tasks.check_schedules()  # same cron slot → deduped on created_at
    assert len(sent) == 1 and sent[0][0][1] == 6
    with S() as s:
        run = s.query(AgentRun).one()
        assert run.platform == "web_search" and run.created_at is not None


# ── LinkedIn ─────────────────────────────────────────────────────────────────

def test_linkedin_cookie_only_reaches_login(monkeypatch):
    _agent_mod("config"); _agent_mod("linkedin_applier")
    agents_main = _agent_mod("main")
    calls = {}
    monkeypatch.setitem(agents_main.CONFIG, "linkedin", {"email": "", "password": ""})
    monkeypatch.setitem(agents_main.CONFIG, "linkedin_cookies", '[{"name":"li_at","value":"x"}]')
    monkeypatch.setattr(agents_main, "create_driver", lambda headless=False: object())
    monkeypatch.setattr(agents_main, "safe_quit", lambda d: None)
    monkeypatch.setattr(agents_main.linkedin_applier, "login",
                        lambda d, e, p, cookies_json=None: calls.setdefault("cookies", cookies_json) and False)
    agents_main.run_linkedin_agent({"name": "A", "keywords": ["analyst"]}, 1, 1, {"applied_urls": []})
    assert calls["cookies"]  # was "Skipping (password not set)" before any login attempt


def test_linkedin_run_stops_when_a_cycle_finds_nothing(monkeypatch):
    _agent_mod("config")
    la = _agent_mod("linkedin_applier")
    pages = []

    def fake_page(driver, config, applied_count, max_jobs, current_keywords=None, dry_run=False):
        pages.append(1)
        if len(pages) == 1:
            config["_li_prepared"] = config.get("_li_prepared", 0) + 1  # one job left for review
        return applied_count
    monkeypatch.setattr(la, "apply_from_search_page", fake_page)
    monkeypatch.setattr(la.time, "sleep", lambda s: None)

    class D:
        def get(self, url):
            pass
    cfg = {"keywords": ["analyst"], "locations": ["India"]}
    assert la.run(D(), cfg, 0, max_jobs=50) == 0
    assert cfg["_li_prepared"] == 1
    assert len(pages) < 20  # used to loop forever with auto_submit off


# ── Structured job records + prepared counts ─────────────────────────────────

def test_report_job_round_trip_to_full_application(db):
    S, uid = db
    from backend.services.apply_decision import report_job
    cfg = {"_last_fit": {"score": 72, "missing": ["SQL"]}, "_tailored_cover_note": "Hi",
           "current_jd_text": "We need SQL and Excel."}
    buf = io.StringIO()
    with redirect_stdout(buf):
        report_job(cfg, "prepared", title="Analyst", company="Acme", url="https://x/1")
    assert "_last_fit" not in cfg and "_tailored_cover_note" not in cfg  # no leak to the next job
    rec = agent_tasks.parse_job_record(buf.getvalue())
    assert rec["status"] == "prepared" and rec["missing_skills"] == ["SQL"]
    with S() as s:
        app_id = agent_tasks._save_application(s, str(uid), "linkedin", rec)
        a = s.get(Application, uuid.UUID(app_id))
        assert a.status == ApplicationStatus.prepared
        assert a.jd_text.startswith("We need SQL") and a.match_score == 72
        assert a.missing_skills == ["SQL"] and a.cover_note_used == "Hi"
        # Submitted later → same row moves to applied.
        agent_tasks._save_application(s, str(uid), "linkedin", {**rec, "status": "applied"})
        s.refresh(a)
        assert a.status == ApplicationStatus.applied and s.query(Application).count() == 1


def test_parse_job_record_rejects_garbage():
    assert agent_tasks.parse_job_record("JOBAGENT_JOB {not json") is None
    assert agent_tasks.parse_job_record('JOBAGENT_JOB {"status": "maybe"}') is None
    assert agent_tasks.parse_job_record("✅ Applied to Acme") is None


# ── Stop without Redis + watchdog ────────────────────────────────────────────

def test_stop_poller_reads_paused_db_row(db, monkeypatch):
    S, uid = db
    rps = _agent_mod("run_phase_subprocess")
    run_id = uuid.uuid4()
    with S() as s:
        s.add(AgentRun(id=run_id, user_id=uid, phase=6, status=RunStatus.running))
        s.commit()
    monkeypatch.setattr(rps.time, "sleep", lambda s: time.sleep(0.01))
    stop = threading.Event()
    rps._start_stop_poller(str(run_id), stop, S)
    with S() as s:
        s.get(AgentRun, run_id).status = RunStatus.paused
        s.commit()
    assert stop.wait(3)  # no Redis needed


def test_watchdog_respects_heartbeat(db):
    S, uid = db
    from backend.services import agent_supervisor
    old = datetime.utcnow() - timedelta(hours=1)
    alive, dead = uuid.uuid4(), uuid.uuid4()
    with S() as s:
        s.add(AgentRun(id=alive, user_id=uid, phase=6, status=RunStatus.running,
                       started_at=old, heartbeat_at=datetime.utcnow()))
        s.add(AgentRun(id=dead, user_id=uid, phase=6, status=RunStatus.running, started_at=old))
        s.commit()
    agent_supervisor._fail_stale_runs()
    with S() as s:
        assert s.get(AgentRun, alive).status == RunStatus.running
        assert s.get(AgentRun, dead).status == RunStatus.failed


# ── JD cache + AI metering ───────────────────────────────────────────────────

def test_jd_analysis_cached_per_process(monkeypatch):
    from backend.services import jd_analyser
    calls = []

    def fake(prompt, **kw):
        calls.append(1)
        return json.dumps({"keywords": ["sql"], "must_haves": ["sql"], "nice_to_haves": [],
                           "seniority": "junior", "archetype": "analyst", "red_flags": []})
    monkeypatch.setattr(jd_analyser, "_default_llm", lambda: fake)
    monkeypatch.setattr(jd_analyser, "_CACHE", {})
    jd = "Analyst role. Must know SQL. " + uuid.uuid4().hex
    a, b = jd_analyser.analyse(jd), jd_analyser.analyse(jd)
    assert len(calls) == 1 and a.must_haves == b.must_haves == ["sql"]
    a.must_haves.append("mutated")
    assert jd_analyser.analyse(jd).must_haves == ["sql"]  # callers get copies


def test_llm_disabled_spends_nothing(monkeypatch):
    import llm_router
    monkeypatch.setattr(llm_router, "_call_groq", lambda *a, **k: pytest.fail("called a provider"))
    assert llm_router.generate("hi", config={"_llm_disabled": True, "groq_api_key": "k"}) is None
    assert "AI disabled" in llm_router.LAST_ERROR


def test_operator_calls_counted_per_run(db):
    S, uid = db
    from backend.services.llm_usage import operator_calls_for_run
    with S() as s:
        for run, payer in [("r1", "operator"), ("r1", "operator"), ("r1", "user"),
                           ("r1", "local"), ("r2", "operator")]:
            s.add(AIRequest(user_id=str(uid), type="llm:writer",
                            input_data={"run_id": run, "billed_to": payer}))
        s.commit()
        assert operator_calls_for_run(s, uid, "r1") == 2


def test_plan_cap_holds_without_redis(monkeypatch):
    from backend.services import apply_decision, rate_limits
    # Own in-memory limiter: the default one writes to whatever Redis is running.
    monkeypatch.setattr(rate_limits, "default_limiter", rate_limits.RateLimiter())
    cfg = {"user_id": "u", "plan_apply_limit": 3, "_applied_today": 2}
    assert apply_decision.rate_ok(cfg, "web_search")
    apply_decision.rate_register(cfg, "web_search")
    with redirect_stdout(io.StringIO()):
        assert not apply_decision.rate_ok(cfg, "web_search")  # 2 earlier today + 1 this run


# ── Per-user tracker + persisted story bank ──────────────────────────────────

def test_tracker_is_per_user(monkeypatch):
    _agent_mod("config"); _agent_mod("linkedin_applier")
    agents_main = _agent_mod("main")
    monkeypatch.setitem(agents_main.CONFIG, "user_id", "user-a")
    a = agents_main._tracker_file()
    monkeypatch.setitem(agents_main.CONFIG, "user_id", "user-b")
    b = agents_main._tracker_file()
    monkeypatch.setitem(agents_main.CONFIG, "user_id", "")
    assert a != b and "user-a" in a and agents_main._tracker_file() == agents_main.TRACKER_FILE


def test_story_bank_survives_a_fresh_app(db, tmp_path):
    S, uid = db
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool
    from backend.database import get_db
    from backend.dependencies import get_current_user
    from backend.routers import career_ops
    with S() as s:
        user = s.get(User, uid)
    aeng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db", poolclass=NullPool)
    AS = sessionmaker(aeng, class_=AsyncSession, expire_on_commit=False)

    def make_client():
        app = FastAPI()
        app.include_router(career_ops.router, prefix="/career-ops")

        async def _db():
            async with AS() as session:
                yield session
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    story = {"title": "Cut report time", "situation": "s", "task": "t", "action": "a", "result": "r"}
    sid = make_client().post("/career-ops/story-bank", json=story).json()["id"]
    fresh = make_client()  # what a restart used to wipe
    assert [x["id"] for x in fresh.get("/career-ops/story-bank").json()] == [sid]
    assert fresh.delete(f"/career-ops/story-bank/{sid}").status_code == 204
    assert fresh.get("/career-ops/story-bank").json() == []
