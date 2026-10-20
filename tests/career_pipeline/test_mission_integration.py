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
    assert replies[0]["result"]["capabilities"] == {"tools": {}, "prompts": {}}
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert {"jobagent_scan_portals", "jobagent_save_mission_targets", "jobagent_tailor_cv", "jobagent_apply_cv_tailoring",
            "jobagent_launch_mission", "jobagent_record_outcome", "jobagent_followups_due"} <= names
    assert all(t["inputSchema"]["type"] == "object" for t in replies[1]["result"]["tools"])
    assert replies[2]["error"]["code"] == -32601


def test_mcp_tool_calls_map_to_api():
    api = FakeApi()
    state = {"api": api}
    call = lambda name, args, i: jobagent_mcp.handle(
        {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}, state)
    assert not call("jobagent_launch_mission", {"missions": ["web_search", "linkedin"], "dry_run": True}, 1)["result"].get("isError")
    assert api.calls[-1] == ("POST", "/agents/run", {"phases": [6, 1], "dry_run": True})
    bad = call("jobagent_launch_mission", {"missions": ["monster"]}, 2)["result"]
    assert bad["isError"] and "missions must be from" in bad["content"][0]["text"]
    call("jobagent_record_outcome", {"application_id": "a b", "status": "interview", "note": "invite"}, 3)
    assert api.calls[-1] == ("PATCH", "/jobs/a%20b/status", {"status": "interview", "note": "invite"})
    call("jobagent_list_applications", {"status": "applied"}, 4)
    assert api.calls[-1] == ("GET", "/jobs?status=applied&limit=21", None)  # one extra row → has_more


def test_mcp_profile_view_hides_internal_data_and_set_targets_saves():
    class Api(FakeApi):
        def call(self, method, path, body=None):
            self.calls.append((method, path, body))
            if path == "/users/profile":
                return {"resume_url": "r.pdf",
                        "extracted_data": {"summary": "Analyst", "skills": ["SQL"],
                                           "_story_bank": [1], "_before_tailor_apply": {}},
                        "autofill_bank": {"phone": "999"},
                        "job_preferences": {"job_titles": ["Business Analyst"], "schedule": {"x": 1}}}
            return {"message": "ok"}
    api = Api()
    view = jobagent_mcp._profile_view(api, {})
    assert view == {"resume": {"summary": "Analyst", "skills": ["SQL"]}, "has_resume": True,
                    "resume_file": "r.pdf",
                    "targets": {"job_titles": ["Business Analyst"]}}  # no autofill/internal keys
    out = jobagent_mcp._set_targets(api, {"job_titles": ["Business Analyst", "Data Analyst"],
                                          "locations": ["Bengaluru", "Remote"], "target_seniority": "entry",
                                          "employment_types": []})
    assert ("POST", "/onboarding/preferences", {"job_titles": ["Business Analyst", "Data Analyst"],
            "locations": ["Bengaluru", "Remote"], "target_seniority": "entry"}) in api.calls
    assert out["saved"]["target_seniority"] == "entry"
    with pytest.raises(jobagent_mcp.ApiError):
        jobagent_mcp._set_targets(api, {})


def test_preferences_accept_target_seniority():
    from backend.routers.onboarding import PreferencesRequest
    assert PreferencesRequest(target_seniority="entry").target_seniority == "entry"
    with pytest.raises(Exception):
        PreferencesRequest(target_seniority="cto")


# ── MCP v2: coverage, safety annotations, composite logic, prompts ───────────

class RouteApi(FakeApi):
    """Fake API answering by (method, path-prefix)."""
    def __init__(self, routes):
        super().__init__()
        self.routes = routes

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        for (m, prefix), val in self.routes.items():
            if m == method and path.startswith(prefix):
                return val(body) if callable(val) else val
        return {}


def _call(api, name, args):
    return jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": name, "arguments": args}}, {"api": api})["result"]


def _text(res):
    return json.loads(res["content"][0]["text"])


def test_every_tool_annotated_and_real_actions_marked():
    tools = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {})["result"]["tools"]
    by = {t["name"]: t for t in tools}
    assert len(tools) >= 40
    assert all("readOnlyHint" in t["annotations"] for t in tools)
    assert by["jobagent_daily_brief"]["annotations"]["readOnlyHint"] is True
    for name in ("jobagent_launch_mission", "jobagent_set_schedule"):
        assert by[name]["annotations"]["destructiveHint"] is True  # clients must confirm
    # Secrets never pass through chat: no tools for passwords, cookies, API keys, account deletion.
    assert not any(k in n for n in by for k in ("password", "cookie", "api_key", "delete_account", "gmail"))


def test_real_launch_requires_confirmation():
    api = RouteApi({("GET", "/agents/preflight"): {"errors": [], "warnings": []},
                    ("GET", "/users/quota"): {"plan": "pro", "ai_tokens_balance": 5},
                    ("GET", "/users/profile"): {"resume_url": "r.pdf", "extracted_data": {"skills": ["SQL"]}},
                    ("POST", "/agents/run"): {"run_ids": ["r1"]}})
    first = _text(_call(api, "jobagent_launch_mission", {"missions": ["web_search"]}))
    assert first["needs_confirmation"] is True and first["ready"] is True
    assert not any(c[1] == "/agents/run" for c in api.calls)  # nothing submitted yet
    _call(api, "jobagent_launch_mission", {"missions": ["web_search"], "confirm": True})
    assert api.calls[-1] == ("POST", "/agents/run", {"phases": [6], "dry_run": False})
    _call(api, "jobagent_launch_mission", {"missions": ["linkedin"], "dry_run": True})  # dry runs need no confirm
    assert api.calls[-1] == ("POST", "/agents/run", {"phases": [1], "dry_run": True})


def test_readiness_explains_fixes():
    api = RouteApi({("GET", "/agents/preflight"): {"errors": ["No job titles or keywords set in your preferences."],
                                                   "warnings": ["naukri: no credentials (that phase will be skipped)."]},
                    ("GET", "/users/quota"): {"plan": "free", "ai_tokens_balance": 0, "scheduling_enabled": False},
                    ("GET", "/users/usage"): {"applies_today": 3, "applies_limit": 20},
                    ("GET", "/users/api-keys"): {"gemini": False, "groq": False},
                    ("GET", "/users/profile"): {"resume_url": "r.pdf", "extracted_data": {}}})
    r = _text(_call(api, "jobagent_readiness_check", {}))
    assert r["ready"] is False and "job-setup" in r["blockers"][0]["fix"]
    assert r["missions_you_can_run"] == ["linkedin"]               # free plan
    assert any("never parsed" in w for w in r["warnings"])
    assert any("AI token balance is 0" in w for w in r["warnings"])
    assert r["schedule"].startswith("Scheduling needs")


def test_daily_brief_builds_todo():
    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat()
    api = RouteApi({("GET", "/agents/runs"): [{"status": "failed", "started_at": now, "applied_count": 2,
                                               "prepared_count": 3}],
                    ("GET", "/jobs?status=prepared"): [{"id": "a", "company": "Acme"}],
                    ("GET", "/jobs?status=interview"): [{"id": "b", "company": "Beta"}],
                    ("GET", "/career-ops/followups/due"): [{"application_id": "c"}],
                    ("GET", "/users/quota"): {"ai_tokens_balance": 7}})
    b = _text(_call(api, "jobagent_daily_brief", {}))
    assert b["last_24h"] == {"runs": 1, "applied": 2, "prepared": 3, "skipped": 0, "failed_runs": 1}
    assert len(b["todo"]) == 4 and b["todo"][0].startswith("Submit 1 prepared")


def test_tools_reuse_saved_job_description():
    api = RouteApi({("GET", "/jobs/app1"): {"jd_text": "Need SQL", "company": "Acme", "job_title": "Analyst"},
                    ("POST", "/career-ops/evaluate"): {"score": 4}})
    _call(api, "jobagent_evaluate_offer", {"application_id": "app1"})
    assert api.calls[-1] == ("POST", "/career-ops/evaluate",
                             {"jd_text": "Need SQL", "company": "Acme", "role": "Analyst"})
    bad = _call(RouteApi({("GET", "/jobs/x"): {}}), "jobagent_tailor_cv", {"application_id": "x"})
    assert bad["isError"] and "no saved job description" in bad["content"][0]["text"]


def test_rejection_patterns_built_from_tracker():
    apps = [{"company": f"C{i}", "job_title": "Analyst", "status": "rejected", "missing_skills": ["SQL"]}
            for i in range(6)]
    api = RouteApi({("GET", "/jobs"): apps, ("POST", "/career-ops/patterns"): {"ok": 1}})
    _call(api, "jobagent_rejection_patterns", {})
    sent = api.calls[-1][2]["applications"]
    assert len(sent) == 6 and sent[0]["blockers"] == ["SQL"]
    few = _call(RouteApi({("GET", "/jobs"): apps[:2]}), "jobagent_rejection_patterns", {})
    assert few["isError"]


def test_prompts_expose_job_workflows():
    lst = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "prompts/list"}, {})["result"]["prompts"]
    names = {p["name"] for p in lst}
    assert {"job-setup", "job-daily", "job-weekly", "job-apply", "job-interview"} <= names
    got = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "prompts/get",
                               "params": {"name": "job-setup", "arguments": {"args": "data analyst, Pune"}}}, {})
    text = got["result"]["messages"][0]["content"]["text"]
    assert "data analyst, Pune" in text and "$ARGUMENTS" not in text and not text.startswith("---")
    assert "error" in jobagent_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "prompts/get",
                                           "params": {"name": "nope"}}, {})


# ── MCP best-practice checks ─────────────────────────────────────────────────

def test_tool_names_prefixed_and_server_named():
    init = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2025-06-18"}}, {})["result"]
    assert init["serverInfo"]["name"] == "jobagent_mcp"
    tools = jobagent_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, {})["result"]["tools"]
    assert all(t["name"].startswith("jobagent_") for t in tools)
    assert len({t["name"] for t in tools}) == len(tools)


def test_protocol_version_negotiation():
    v = lambda asked: jobagent_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                           "params": {"protocolVersion": asked}}, {})["result"]["protocolVersion"]
    assert v("2025-03-26") == "2025-03-26"                   # supported → echoed
    assert v("2099-01-01") == jobagent_mcp.PROTOCOL_VERSION  # unknown → ours


def test_missing_required_arg_is_actionable():
    res = _call(FakeApi(), "jobagent_mission_logs", {})
    assert res["isError"] and "missing run_id" in res["content"][0]["text"]


def test_pagination_metadata():
    rows = [{"id": str(i)} for i in range(6)]
    api = RouteApi({("GET", "/jobs"): lambda b: rows})
    page = _text(_call(api, "jobagent_list_applications", {"limit": 5}))
    assert page["count"] == 5 and page["has_more"] is True and page["next_offset"] == 5
    assert api.calls[-1][1] == "/jobs?limit=6"
    api2 = RouteApi({("GET", "/jobs"): lambda b: rows[:2]})
    last = _text(_call(api2, "jobagent_list_applications", {"limit": 5, "offset": 5}))
    assert last["has_more"] is False and last["next_offset"] is None and api2.calls[-1][1] == "/jobs?limit=6&offset=5"


def test_structured_content_and_size_cap():
    small = jobagent_mcp._result({"a": 1})
    assert small["structuredContent"] == {"a": 1}
    assert "structuredContent" not in jobagent_mcp._result([1, 2])   # spec: objects only
    big = jobagent_mcp._result({"x": "y" * (jobagent_mcp.CHARACTER_LIMIT + 10)})
    text = big["content"][0]["text"]
    assert len(text) < jobagent_mcp.CHARACTER_LIMIT + 300 and "truncated" in text
    assert "structuredContent" not in big
