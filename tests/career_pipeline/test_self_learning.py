"""End-to-end test of the self-resolution (self-learning) + logging pipeline.

Verifies against a REAL in-memory SQLite DB (not mocks):
  * _log_event writes an AgentLog row (the logging pipeline);
  * _learn_from_run_logs turns run errors into deterministic future rules and
    persists them onto the profile's agent_custom_instructions, with no-Gemini
    fallback, dedup, and the MAX_RULES growth cap.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401 — register all models on Base
from backend.database import Base
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.models.agent_run import AgentRun, AgentLog
from backend.workers import agent_tasks as at


@pytest.fixture()
def session(monkeypatch):
    # Force the deterministic (no-Gemini) self-learning path so the test is
    # hermetic regardless of any SYSTEM_GEMINI_KEY in the environment.
    from backend.config import settings
    monkeypatch.setattr(settings, "system_gemini_key", "", raising=False)
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _seed(session, prefs=None):
    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex}@e.com", name="A", hashed_password="x")
    p = UserProfile(id=uuid.uuid4(), user_id=u.id, job_preferences=prefs if prefs is not None else {})
    r = AgentRun(id=uuid.uuid4(), user_id=u.id, phase=1)
    session.add_all([u, p, r])
    session.commit()
    return u, p, r


# ── logging pipeline ─────────────────────────────────────────────────────────

def test_log_event_writes_a_row(session):
    _u, _p, r = _seed(session)
    at._log_event(session, str(r.id), "error", "CAPTCHA challenge detected")
    rows = session.query(AgentLog).filter(AgentLog.run_id == r.id).all()
    assert len(rows) == 1
    assert rows[0].event_type == "error"
    assert "CAPTCHA" in rows[0].message


def test_log_event_truncates_long_messages(session):
    _u, _p, r = _seed(session)
    at._log_event(session, str(r.id), "info", "x" * 5000)
    row = session.query(AgentLog).filter(AgentLog.run_id == r.id).one()
    assert len(row.message) <= 2048


# ── self-learning / self-resolution ──────────────────────────────────────────

def test_no_logs_returns_none(session):
    _u, _p, r = _seed(session)
    assert at._learn_from_run_logs(session, str(_u.id), str(r.id)) is None


def test_captcha_error_produces_and_persists_rule(session):
    u, p, r = _seed(session)
    at._log_event(session, str(r.id), "login_challenge", "Security challenge / CAPTCHA on linkedin")
    advice = at._learn_from_run_logs(session, str(u.id), str(r.id))
    assert advice and "captcha" in advice.lower()
    session.refresh(p)
    instr = (p.job_preferences or {}).get("agent_custom_instructions", "")
    assert "captcha" in instr.lower()


def test_resume_upload_error_produces_rule(session):
    u, p, r = _seed(session)
    at._log_event(session, str(r.id), "error", "resume file upload failed on greenhouse")
    advice = at._learn_from_run_logs(session, str(u.id), str(r.id))
    assert advice and "resume" in advice.lower()


def test_rules_are_deduped_across_runs(session):
    u, p, r = _seed(session)
    at._log_event(session, str(r.id), "error", "CAPTCHA challenge")
    at._learn_from_run_logs(session, str(u.id), str(r.id))
    session.refresh(p)
    first = (p.job_preferences or {}).get("agent_custom_instructions", "")
    # Second run, same error → must NOT duplicate the rule.
    r2 = AgentRun(id=uuid.uuid4(), user_id=u.id, phase=1)
    session.add(r2); session.commit()
    at._log_event(session, str(r2.id), "error", "CAPTCHA challenge again")
    at._learn_from_run_logs(session, str(u.id), str(r2.id))
    session.refresh(p)
    second = (p.job_preferences or {}).get("agent_custom_instructions", "")
    assert second.lower().count("when a login challenge") == 1


def test_instructions_capped_at_25_rules(session):
    u, p, r = _seed(session)
    # Pre-load 30 distinct rules; a new run must trim back to <=25.
    p.job_preferences = {"agent_custom_instructions": "\n".join(f"rule {i}" for i in range(30))}
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(p, "job_preferences"); session.commit()
    at._log_event(session, str(r.id), "error", "resume upload failed")
    at._learn_from_run_logs(session, str(u.id), str(r.id))
    session.refresh(p)
    lines = [l for l in (p.job_preferences or {}).get("agent_custom_instructions", "").splitlines() if l.strip()]
    assert len(lines) <= 25
