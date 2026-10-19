"""After-apply features: follow-ups, skill gaps, outcomes from email, ATS check.

Pure logic in backend.services.followthrough is tested directly; the career_ops
endpoints run against a real SQLite DB with auth overridden.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import backend.models  # noqa: F401 — register tables
from backend.database import Base, get_db
from backend.dependencies import get_current_user
from backend.models.application import Application, ApplicationStatus, JobOutcome
from backend.models.user import User
from backend.models.tailored_resume import TailoredResume as TailoredResumeRow
from backend.routers import career_ops, jobs
from backend.services import followthrough as ft
from backend.services.career_schemas import TailoredResume
from backend.services.resume_pdf import parse_problems, render_to_path

NOW = datetime(2026, 10, 19, 12, 0)


def _app(status="applied", days_ago=10, history=None, company="Acme", **kw):
    return {"id": uuid.uuid4(), "company": company, "job_title": "Analyst", "status": status,
            "applied_at": NOW - timedelta(days=days_ago), "history": history or [], **kw}


# ── Follow-ups ───────────────────────────────────────────────────────────────

def test_followups_due_respects_cadence_and_cap():
    quiet = _app(days_ago=8)                                   # applied, 7d cadence → due
    fresh = _app(days_ago=3)                                   # not yet
    recent_activity = _app(days_ago=20, history=[{"type": "status_change",
                                                  "timestamp": (NOW - timedelta(days=2)).isoformat()}])
    capped = _app(days_ago=30, history=[{"type": ft.FOLLOWUP_EVENT,
                                         "timestamp": (NOW - timedelta(days=20)).isoformat()}] * 2)
    interview = _app(status=ApplicationStatus.interview, days_ago=2)  # 1d cadence → due
    rejected = _app(status="rejected", days_ago=60)
    due = ft.followups_due([quiet, fresh, recent_activity, capped, interview, rejected], now=NOW)
    assert {d["application_id"] for d in due} == {str(quiet["id"]), str(interview["id"])}
    assert due[0]["days_quiet"] >= due[1]["days_quiet"]


# ── Skill gaps ───────────────────────────────────────────────────────────────

def test_skill_gaps_counts_and_weights_interviews():
    apps = [_app(missing_skills=["SQL", "Excel"]), _app(missing_skills=["sql"]),
            _app(status="interview", missing_skills=["Tableau"])]
    gaps = ft.skill_gaps(apps)
    assert gaps[0] == {"skill": "SQL", "weight": 2}
    assert {"skill": "Tableau", "weight": 2} in gaps


# ── Outcomes from email ──────────────────────────────────────────────────────

@pytest.mark.parametrize("subject,body,expected", [
    ("Your application", "Unfortunately we will not be moving forward after the interview.", "rejected"),
    ("Interview invitation", "Please share your availability for a call.", "interview"),
    ("Next steps", "Please complete this HackerRank assessment.", "shortlisted"),
    ("Offer", "We are pleased to extend an offer.", "offer"),
    ("Newsletter", "Top 10 jobs this week", None),
])
def test_classify_email(subject, body, expected):
    assert ft.classify_email(subject, body) == expected


def test_propose_outcomes_matches_one_company_and_never_downgrades():
    acme = _app(company="Acme Technologies Pvt Ltd")
    globex = _app(company="Globex", status="interview")
    emails = [
        {"from": "jobs@acme.com", "subject": "Interview with Acme", "body": "", "date": "2026-10-10T09:00"},
        {"from": "hr@globex.com", "subject": "Globex: next round", "body": "assessment", "date": "2026-10-11"},
        {"from": "x@y.com", "subject": "Interview", "body": "Acme and Globex", "date": "2026-10-12"},
    ]
    props = ft.propose_outcomes(emails, [acme, globex])
    # Globex: shortlisted would be a downgrade from interview; the third mail is ambiguous.
    assert len(props) == 1
    assert props[0]["application_id"] == str(acme["id"])
    assert props[0]["proposed_status"] == "interview"
    assert props[0]["evidence"]["from"] == "jobs@acme.com"


def test_rejection_can_follow_interview():
    app = _app(company="Globex", status="interview")
    props = ft.propose_outcomes([{"from": "hr@globex.com", "subject": "Update",
                                  "body": "Unfortunately the position has been filled."}], [app])
    assert props[0]["proposed_status"] == "rejected"


# ── ATS parseability ─────────────────────────────────────────────────────────

def test_parse_problems_on_good_and_bad_pdf(tmp_path):
    good = render_to_path(TailoredResume(name="Asha Rao", email="asha@example.com",
                                         summary="Analyst who builds dashboards in SQL and Excel.",
                                         skills=["SQL", "Excel"]), str(tmp_path / "good.pdf"))
    assert parse_problems(good, must_contain=("Asha Rao", "asha@example.com")) == []
    assert parse_problems(good, must_contain=("Someone Else",)) == ["'Someone Else' not found in extracted text"]
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert parse_problems(str(bad))[0].startswith("text extraction failed")


# ── Endpoints against a real DB ──────────────────────────────────────────────

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
        tr = TailoredResumeRow(user_id=user.id, jd_hash="h1", pdf_path="x.pdf",
                               resume_json={"summary": "Built SQL dashboards at Beta", "skills": ["SQL"]})
        s.add(tr)
        s.flush()
        acme = Application(user_id=user.id, platform="linkedin", job_title="Analyst", company="Acme",
                           job_hash="h1", applied_at=datetime.utcnow() - timedelta(days=9),
                           missing_skills=["SQL"], history=[], tailored_resume_id=tr.id,
                           cover_note_used="I love Acme's data team.", jd_text="Analyst role")
        s.add(acme)
        s.commit()
    aeng = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    ASession = sessionmaker(aeng, class_=AsyncSession, expire_on_commit=False)

    async def _db():
        async with ASession() as session:
            yield session
            await session.commit()

    app = FastAPI()
    app.include_router(career_ops.router, prefix="/career-ops")
    app.include_router(jobs.router, prefix="/jobs")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(career_ops, "_ai", lambda prompt, u: '{"urgency": "OVERDUE", "email_draft": {"subject": "Hi", "body": "b"}}')
    return TestClient(app), S, acme.id


def test_followup_persists_and_caps(client):
    c, S, app_id = client
    due = c.get("/career-ops/followups/due").json()
    assert [d["application_id"] for d in due] == [str(app_id)]
    body = {"company": "Acme", "role": "Analyst", "status": "applied", "days_since_action": 9,
            "application_id": str(app_id)}
    assert c.post("/career-ops/followup", json=body).status_code == 200
    assert c.post("/career-ops/followup", json=body).status_code == 200
    assert c.post("/career-ops/followup", json=body).status_code == 409   # capped at 2
    drafts = c.get(f"/career-ops/followups/{app_id}").json()
    assert len(drafts) == 2 and drafts[0]["urgency"] == "OVERDUE"         # survives in the DB
    assert c.get("/career-ops/followups/due").json() == []


def test_gmail_scan_proposes_then_apply_writes_outcome(client, monkeypatch):
    c, S, app_id = client
    monkeypatch.setattr(ft, "fetch_gmail", lambda *a, **k: [
        {"from": "talent@acme.com", "subject": "Interview with Acme", "body": "", "date": "2026-10-18"}])
    r = c.post("/career-ops/outcomes/gmail-scan",
               json={"email": "u@gmail.com", "app_password": "abcd efgh ijkl mnop"}).json()
    assert r["scanned"] == 1
    [p] = r["proposals"]
    with S() as s:  # proposal only — nothing written yet
        assert s.get(Application, app_id).status == ApplicationStatus.applied
    ok = c.post("/career-ops/outcomes/apply", json={"updates": [
        {"application_id": p["application_id"], "status": p["proposed_status"],
         "evidence": p["evidence"]["subject"]}]})
    assert ok.status_code == 200
    with S() as s:
        assert s.get(Application, app_id).status == ApplicationStatus.interview
        outcome = s.execute(select(JobOutcome).where(JobOutcome.application_id == app_id)).scalar_one()
        assert outcome.outcome == "interview"   # feeds response_rates / fit scoring


def test_interview_prep_uses_submitted_materials(client, monkeypatch):
    c, S, app_id = client
    seen = {}

    def fake_prep(resume_summary, jd_text, company, n_questions=10, user_key=None):
        seen["summary"] = resume_summary
        return {"questions": [{"question": "q", "model_answer": "a"}]}
    import backend.services.gemini_service as gs
    monkeypatch.setattr(gs, "generate_interview_prep", fake_prep)
    c.patch(f"/jobs/{app_id}/status", json={"status": "shortlisted", "note": "Liked the SQL project"})
    c.patch(f"/jobs/{app_id}/status", json={"status": "interview"})  # prep exists → not regenerated
    assert "Built SQL dashboards at Beta" in seen["summary"]   # the tailored resume that was sent
    assert "I love Acme's data team." in seen["summary"]       # the cover note that was sent
    with S() as s:
        assert s.get(Application, app_id).interview_prep["questions"]
    # Second round: clear prep, regenerate — earlier-round feedback is now included.
    with S() as s:
        a = s.get(Application, app_id)
        a.interview_prep, a.status = None, ApplicationStatus.shortlisted
        s.commit()
    c.patch(f"/jobs/{app_id}/status", json={"status": "interview"})
    assert "Liked the SQL project" in seen["summary"]


def test_skill_gaps_endpoint(client):
    c, _, _ = client
    assert c.get("/career-ops/skill-gaps").json() == [{"skill": "SQL", "weight": 1}]
