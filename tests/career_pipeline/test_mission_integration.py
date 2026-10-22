"""Portal Scan → mission targets, Tailor CV → profile, and the JobAgent MCP server."""
from __future__ import annotations

import io
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.dependencies import get_current_user
from backend.models.profile import UserProfile
from backend.models.user import User
from backend.routers import career_ops

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "mcp_server"))
import jobagent_mcp  # noqa: E402


@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
    ("https://job-boards.greenhouse.io/Figma/jobs/123", ("greenhouse", "figma")),
    ("https://boards.greenhouse.io/embed/job_board?for=groww", ("greenhouse", "groww")),
    ("https://jobs.lever.co/razorpay/abc-123", ("lever", "razorpay")),
    ("https://careers.google.com/jobs", None),
])
def test_parse_board(url, expected):
    assert career_ops.parse_board(url) == expected


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "t.db"
    sync = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync)
    S = sessionmaker(sync, expire_on_commit=False)
    with S() as s:
        user = User(email="u@example.com", hashed_password="x", name="U")
        s.add(user)
        s.flush()
        s.add(UserProfile(user_id=user.id, job_preferences={"target_companies": ["Swiggy"]},
                          autofill_bank={"skills": "Excel"},
                          extracted_data={"summary": "Old summary", "skills": ["Excel"],
                                          "experience": [{"company": "Beta", "role": "Intern",
                                                          "description": "Made reports."}]}))
        s.commit()
    aeng = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    ASession = sessionmaker(aeng, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with ASession() as session:
            yield session
            await session.commit()

    app = FastAPI()
    app.include_router(career_ops.router, prefix="/career-ops")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user

    async def fake_open_jobs(kind, slug):
        return {"stripe": 42, "razorpay": 7}.get(slug)  # anything else "doesn't exist"
    monkeypatch.setattr(career_ops, "_open_jobs", fake_open_jobs)
    return TestClient(app), S, user.id


def _profile(S, uid):
    with S() as s:
        return s.query(UserProfile).filter_by(user_id=uid).one()


def test_save_targets_verifies_boards_and_merges(client):
    c, S, uid = client
    r = c.post("/career-ops/mission-targets", json={"targets": [
        {"company": "Stripe", "portals": ["https://boards.greenhouse.io/stripe", "https://stripe.com/jobs"]},
        {"company": "Razorpay", "portals": ["https://jobs.lever.co/razorpay"]},
        {"company": "Madeup", "portals": ["https://boards.greenhouse.io/madeupco"]},
        {"company": "swiggy", "portals": []},  # already saved (case-insensitive)
    ]}).json()
    assert r["companies"] == ["Swiggy", "Stripe", "Razorpay", "Madeup"]
    assert {(b["slug"], b["open_jobs"]) for b in r["boards"]} == {("stripe", 42), ("razorpay", 7)}
    assert r["unverified_portals"] == ["greenhouse:madeupco"]
    # Saving again doesn't duplicate.
    again = c.post("/career-ops/mission-targets", json={"targets": [
        {"company": "Stripe", "portals": ["https://boards.greenhouse.io/stripe"]}]}).json()
    assert len(again["boards"]) == 2
    prefs = _profile(S, uid).job_preferences
    assert prefs["target_boards"][0]["kind"] == "greenhouse"
    # Remove drops both the name and its board.
    left = c.delete("/career-ops/mission-targets/stripe").json()
    assert "Stripe" not in left["companies"] and all(b["slug"] != "stripe" for b in left["boards"])


def test_mission_config_carries_target_boards(client):
    _, S, uid = client
    from backend.workers.agent_tasks import _build_config
    p = _profile(S, uid)
    p.job_preferences = {**p.job_preferences, "target_boards": [{"kind": "lever", "slug": "acme"}]}
    with S() as s:
        u = s.get(User, uid)
    assert _build_config(u, p)["web_search"]["target_boards"] == [{"kind": "lever", "slug": "acme"}]


def test_tailor_apply_and_undo(client, monkeypatch):
    c, S, uid = client
    monkeypatch.setattr(career_ops, "_ai", lambda prompt, u: json.dumps({
        "tailored_summary": "Analyst who automates reporting.", "keywords_to_inject": ["SQL"],
        "bullet_rewrites": [{"experience_index": 0, "rewrite": "Built 12 weekly reports."},
                            {"experience_index": 5, "rewrite": "ghost entry"}]}))
    sug = c.post("/career-ops/tailor-cv", json={"jd_text": "x" * 50}).json()
    assert sug["bullet_rewrites"] == [{"experience_index": 0, "rewrite": "Built 12 weekly reports.",
                                       "role": "Intern", "company": "Beta", "original": "Made reports."}]
    ok = c.post("/career-ops/tailor-cv/apply", json={
        "summary": sug["tailored_summary"], "skills_add": ["SQL", "excel"],
        "rewrites": [{"experience_index": 0, "rewrite": "Built 12 weekly reports."}]})
    assert ok.status_code == 200
    p = _profile(S, uid)
    assert p.extracted_data["summary"] == "Analyst who automates reporting."
    assert p.extracted_data["skills"] == ["Excel", "SQL"]                     # no duplicate 'excel'
    assert p.extracted_data["experience"][0]["description"] == "Built 12 weekly reports."
    assert p.autofill_bank["skills"] == "Excel, SQL"                          # missions read this first
    assert c.post("/career-ops/tailor-cv/apply", json={
        "rewrites": [{"experience_index": 9, "rewrite": "x"}]}).status_code == 400
    assert c.post("/career-ops/tailor-cv/undo").status_code == 200
    p = _profile(S, uid)
    assert p.extracted_data["summary"] == "Old summary"
    assert p.extracted_data["experience"][0]["description"] == "Made reports."
    assert p.autofill_bank["skills"] == "Excel"
    assert c.post("/career-ops/tailor-cv/undo").status_code == 404


# ── MCP server ───────────────────────────────────────────────────────────────

class FakeApi:
    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {"ok": True}


def _rpc(lines):
    out = io.StringIO()
    jobagent_mcp.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in lines)), out)
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_mcp_handshake_and_tool_list():
    replies = _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nope"},
    ])
    assert [r["id"] for r in replies] == [1, 2, 3]   # the notification got no reply
    assert replies[0]["result"]["capabilities"] == {"tools": {}}
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert {"scan_portals", "save_mission_targets", "tailor_cv", "apply_cv_tailoring",
            "launch_mission", "record_outcome", "followups_due"} <= names
    assert all(t["inputSchema"]["type"] == "object" for t in replies[1]["result"]["tools"])
    assert replies[2]["error"]["code"] == -32601


def test_mcp_tool_calls_map_to_api():
    api = FakeApi()
    state = {"api": api}
    call = lambda name, args, i: jobagent_mcp.handle(
        {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}, state)
    assert not call("launch_mission", {"missions": ["web_search", "linkedin"], "dry_run": True}, 1)["result"].get("isError")
    assert api.calls[-1] == ("POST", "/agents/run", {"phases": [6, 1], "dry_run": True})
    bad = call("launch_mission", {"missions": ["monster"]}, 2)["result"]
    assert bad["isError"] and "missions must be from" in bad["content"][0]["text"]
    call("record_outcome", {"application_id": "a b", "status": "interview", "note": "invite"}, 3)
    assert api.calls[-1] == ("PATCH", "/jobs/a%20b/status", {"status": "interview", "note": "invite"})
    call("list_applications", {"status": "applied"}, 4)
    assert api.calls[-1] == ("GET", "/jobs?status=applied&limit=50", None)


def test_mcp_daily_schedule_and_progress():
    api = FakeApi()
    state = {"api": api}
    call = lambda name, args, i: jobagent_mcp.handle(
        {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}, state)
    # 09:30 in India (+05:30) is 04:00 UTC.
    r = call("schedule_daily_missions", {"missions": ["linkedin", "wellfound", "web_search"],
                                         "time": "09:30", "utc_offset": "+05:30"}, 1)["result"]
    assert not r.get("isError")
    assert api.calls[-1] == ("POST", "/agents/schedule", {"cron": "0 4 * * *", "phases": [1, 3, 6], "enabled": True})
    call("schedule_daily_missions", {"missions": ["linkedin"], "time": "01:00", "utc_offset": "+05:30"}, 2)
    assert api.calls[-1][2]["cron"] == "30 19 * * *"   # wraps to the previous UTC day
    call("schedule_daily_missions", {"missions": ["linkedin"], "time": "20:00", "utc_offset": "-05:00"}, 3)
    assert api.calls[-1][2]["cron"] == "0 1 * * *"
    bad = call("schedule_daily_missions", {"missions": ["linkedin"], "time": "25:00"}, 4)["result"]
    assert bad["isError"]
    call("progress_report", {}, 5)
    assert [c[1] for c in api.calls[-2:]] == ["/jobs/analytics", "/agents/runs"]
    call("list_applications", {"platform": "wellfound"}, 6)
    assert api.calls[-1] == ("GET", "/jobs?platform=wellfound&limit=50", None)
    call("check_ready", {}, 7)
    assert api.calls[-1] == ("GET", "/agents/preflight", None)


def test_mcp_get_schedule_names_missions():
    class SchedApi(FakeApi):
        def call(self, method, path, body=None):
            return {"cron": "0 4 * * *", "phases": [1, 6], "enabled": True}
    state = {"api": SchedApi()}
    r = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "get_schedule", "arguments": {}}}, state)
    assert json.loads(r["result"]["content"][0]["text"])["missions"] == ["linkedin", "web_search"]
