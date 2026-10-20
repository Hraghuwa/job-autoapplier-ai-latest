"""Claude-native mode: AI endpoints hand their prompt to the caller's LLM, save-only
endpoints store the result, and missions' unanswered questions feed the answer bank."""
from __future__ import annotations

import io
import json
import os
import sys
import uuid
from contextlib import redirect_stdout

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.dependencies import get_current_user
from backend.models.application import Application, ApplicationStatus
from backend.models.profile import UserProfile
from backend.models.user import User
from backend.routers import ai, career_ops, jobs
from backend.services.claude_native import BriefOnly, brief_mode, brief_response
from backend.workers import agent_tasks

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server"))
import jobagent_mcp  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    sync = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync)
    S = sessionmaker(sync, expire_on_commit=False)
    with S() as s:
        user = User(email="u@example.com", hashed_password="x", name="U", plan="pro", ai_tokens_balance=5)
        s.add(user)
        s.flush()
        s.add(UserProfile(user_id=user.id, autofill_bank={"Notice period (days)": "30", "phone": ""},
                          extracted_data={"summary": "Analyst", "skills": ["SQL"],
                                          "experience": [{"company": "Beta", "role": "Intern", "description": "Reports."}]}))
        app_row = Application(user_id=user.id, platform="web_search", job_title="Analyst", company="Acme",
                              job_hash="h1", jd_text="Need SQL and Power BI.", status=ApplicationStatus.prepared,
                              history=[{"type": "needs_answers", "data": {"questions": [
                                  "Expected CTC (annual, INR)", "Notice period (days)"]}}])
        s.add(app_row)
        s.commit()
        app_id = app_row.id
    aeng = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    AS = sessionmaker(aeng, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with AS() as session:
            yield session
            await session.commit()

    app = FastAPI()

    @app.exception_handler(BriefOnly)
    async def _h(_r: Request, exc: BriefOnly):
        return JSONResponse(brief_response(exc.prompt))

    app.include_router(career_ops.router, prefix="/career-ops", dependencies=[Depends(brief_mode)])
    app.include_router(ai.router, prefix="/ai", dependencies=[Depends(brief_mode)])
    app.include_router(jobs.router, prefix="/jobs")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    # Any real model call is a test failure in brief mode.
    import llm_router
    monkeypatch.setattr(llm_router, "generate", lambda *a, **k: pytest.fail("model called in brief mode"))
    return TestClient(app), S, user, app_id


# ── brief mode ───────────────────────────────────────────────────────────────

def test_brief_returns_full_prompt_and_spends_nothing(env):
    c, S, user, app_id = env
    r = c.post("/career-ops/tailor-cv?brief=true", json={"jd_text": "Need SQL and Power BI for dashboards."}).json()
    assert r["mode"] == "claude_native"
    assert "Power BI" in r["instructions"] and "Reports." in r["instructions"]  # JD + resume in the brief
    r2 = c.post("/ai/enhance-summary?brief=true", json={"text": "I like data"}).json()
    assert r2["mode"] == "claude_native" and "I like data" in r2["instructions"]
    with S() as s:
        assert s.get(User, user.id).ai_tokens_balance == 5  # no token consumed


def test_no_brief_flag_still_uses_server_ai(env, monkeypatch):
    c, _, _, _ = env
    monkeypatch.setattr(career_ops, "_ai", lambda prompt, u: '{"suggestions": []}')
    assert c.post("/career-ops/scan", json={"query": "analyst"}).json() == {"suggestions": []}


def test_interview_prep_brief_then_save(env):
    c, _, _, app_id = env
    r = c.get(f"/jobs/{app_id}/interview-prep?brief=true").json()
    assert r["mode"] == "claude_native" and "Acme" in r["instructions"]
    saved = c.put(f"/jobs/{app_id}/interview-prep", json={
        "questions": [{"question": "Why SQL?", "model_answer": "Because..."}], "company_brief": "Acme sells."}).json()
    assert saved == {"saved": True, "questions": 1}
    assert c.get(f"/jobs/{app_id}/interview-prep").json()["company_brief"] == "Acme sells."


# ── save-only endpoints ──────────────────────────────────────────────────────

def test_save_evaluation_and_stories(env):
    c, _, _, _ = env
    ev = {"score": 4.2, "blocks": {"F_interview_prep": {"stories": [{"title": "Cut report time"}]}}}
    rec = c.post("/career-ops/evaluations", json={"evaluation": ev, "company": "Acme", "role": "Analyst"}).json()
    assert rec["evaluation"]["score"] == 4.2
    assert [e["company"] for e in c.get("/career-ops/evaluations").json()] == ["Acme"]
    assert [s["title"] for s in c.get("/career-ops/story-bank").json()] == ["Cut report time"]


def test_save_followup_draft_respects_cap(env):
    c, _, _, app_id = env
    body = {"urgency": "OVERDUE", "email_draft": {"subject": "Hi", "body": "Checking in"}}
    assert c.post(f"/career-ops/followups/{app_id}/draft", json=body).json() == {"saved": True}
    assert c.post(f"/career-ops/followups/{app_id}/draft", json=body).status_code == 200
    assert c.post(f"/career-ops/followups/{app_id}/draft", json=body).status_code == 409
    assert len(c.get(f"/career-ops/followups/{app_id}").json()) == 2


# ── answer bank ──────────────────────────────────────────────────────────────

def test_answer_bank_lists_real_gaps(env):
    c, _, _, _ = env
    b = c.get("/career-ops/answer-bank").json()
    assert b["answers"] == {"Notice period (days)": "30"}                        # empty values hidden
    assert [q["question"] for q in b["unanswered_from_missions"]] == ["Expected CTC (annual, INR)"]
    assert b["unanswered_from_missions"][0]["companies"] == ["Acme"]
    assert "Notice period (days)" not in b["standard_questions_missing"]
    assert "Expected CTC (annual, INR)" in b["standard_questions_missing"]


def test_mission_questions_reach_application(env):
    _, S, user, _ = env
    from backend.services.apply_decision import report_job
    cfg = {"_unanswered": ["Are you willing to relocate?"], "current_jd_text": "JD"}
    buf = io.StringIO()
    with redirect_stdout(buf):
        report_job(cfg, "prepared", title="Analyst", company="Globex", url="https://x/2")
    rec = agent_tasks.parse_job_record(buf.getvalue())
    assert rec["questions"] == ["Are you willing to relocate?"] and "_unanswered" not in cfg
    with S() as s:
        app_id = agent_tasks._save_application(s, str(user.id), "web_search", rec)
        from backend.schemas.application import ApplicationDetail
        d = ApplicationDetail.model_validate(s.get(Application, uuid.UUID(app_id)))
        assert d.needs_answers == ["Are you willing to relocate?"]


# ── MCP side ─────────────────────────────────────────────────────────────────

class Api:
    def __init__(self, routes):
        self.routes, self.calls, self.brief = routes, [], False

    def call(self, method, path, body=None):
        if self.brief:
            path += ("&" if "?" in path else "?") + "brief=true"
        self.calls.append((method, path, body))
        for (m, prefix), val in self.routes.items():
            if m == method and path.startswith(prefix):
                return val
        return {}


def _call(api, name, args):
    res = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": name, "arguments": args}}, {"api": api})["result"]
    return json.loads(res["content"][0]["text"])


def test_thinking_tools_are_claude_native_by_default():
    api = Api({("POST", "/career-ops/tailor-cv"): {"mode": "claude_native", "instructions": "PROMPT"}})
    out = _call(api, "jobagent_tailor_cv", {"jd_text": "JD"})
    assert api.calls[-1][1] == "/career-ops/tailor-cv?brief=true"
    assert out["instructions"] == "PROMPT" and "jobagent_apply_cv_tailoring" in out["then"]
    assert api.brief is False  # flag never leaks into the next tool
    _call(api, "jobagent_tailor_cv", {"jd_text": "JD", "use_server_ai": True})
    assert api.calls[-1] == ("POST", "/career-ops/tailor-cv", {"jd_text": "JD"})


def test_every_thinking_tool_offers_server_fallback():
    tools = {t["name"]: t for t in jobagent_mcp.TOOLS}
    for name in jobagent_mcp.THINK:
        assert "use_server_ai" in tools[name]["schema"]["properties"], name


def test_review_prepared_matches_saved_answers():
    api = Api({("GET", "/jobs?status=prepared"): [{"id": "a1", "company": "Acme", "job_title": "Analyst",
                                                   "job_url": "https://acme/jobs/1"}],
               ("GET", "/career-ops/answer-bank"): {"answers": {"Notice period (days)": "30"}},
               ("GET", "/jobs/a1"): {"needs_answers": ["Notice Period (days)?", "Expected CTC"]}})
    out = _call(api, "jobagent_review_prepared", {})
    qs = out["prepared"][0]["questions"]
    assert qs[0] == {"question": "Notice Period (days)?", "saved_answer": "30"}   # normalised match
    assert out["unanswered_questions"] == ["Expected CTC"]
    assert out["prepared"][0]["url"] == "https://acme/jobs/1"


def test_save_answers_merges_into_bank():
    api = Api({})
    out = _call(api, "jobagent_save_answers", {"answers": {"Expected CTC": "6 LPA"}})
    assert api.calls[-1] == ("POST", "/onboarding/autofill", {"autofill_bank": {"Expected CTC": "6 LPA"}})
    assert out == {"saved": ["Expected CTC"]}
