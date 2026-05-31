"""Tests for backend.services.response_rates — Phase F.

Contract:
    response_rates.by_tailored_resume(session, user_id) -> list of dicts
        each dict: {tailored_resume_id, applied, callbacks, response_rate, archetype}
    response_rates.by_archetype(session, user_id) -> list of dicts

Where "callback" = application whose outcome.outcome is any of:
    "viewed", "shortlisted", "interview", "offer"
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.services import response_rates
import backend.models  # noqa


@pytest.fixture()
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/test.db", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(eng, expire_on_commit=False)


def _seed_user(session):
    from backend.models.user import User
    u = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:6]}@x.com",
            hashed_password="x", name="Test")
    session.add(u); session.commit(); return u


def _seed_tailored(session, user_id, archetype, jd_hash):
    from backend.models.tailored_resume import TailoredResume as TR
    row = TR(id=uuid.uuid4(), user_id=user_id, jd_hash=jd_hash,
             jd_signature={"archetype": archetype}, resume_json={},
             pdf_path="/tmp/x.pdf", profile_ver=1, jd_coverage=0.8)
    session.add(row); session.commit(); return row


def _seed_application(session, user_id, tailored_id, outcome=None):
    from backend.models.application import Application, JobOutcome, ApplicationStatus
    from datetime import datetime
    app = Application(id=uuid.uuid4(), user_id=user_id, platform="x",
                      job_title="t", company="c", job_hash=uuid.uuid4().hex,
                      status=ApplicationStatus.applied)
    # add column tailored_resume_id (we'll add via raw SQL since model edit
    # is part of Phase E)
    session.add(app); session.flush()
    session.execute(__import__("sqlalchemy").text(
        "UPDATE applications SET tailored_resume_id = :tid WHERE id = :aid"
    ), {"tid": tailored_id.hex, "aid": app.id.hex})
    if outcome:
        oc = JobOutcome(id=uuid.uuid4(), application_id=app.id, outcome=outcome)
        session.add(oc)
    session.commit()
    return app


# ── RED 1: by_tailored_resume aggregates correctly ──────────────────────────
def test_by_tailored_resume_counts_applies_and_callbacks(session_factory):
    with session_factory() as s:
        # Add tailored_resume_id column (Phase E will do this in production)
        # tailored_resume_id is now in the model — create_all added it.
        pass

        u = _seed_user(s)
        tr1 = _seed_tailored(s, u.id, "backend python", "jdh1")
        tr2 = _seed_tailored(s, u.id, "ml engineer",    "jdh2")
        # tr1: 3 applies, 1 callback (interview)
        _seed_application(s, u.id, tr1.id, outcome=None)
        _seed_application(s, u.id, tr1.id, outcome="rejected")
        _seed_application(s, u.id, tr1.id, outcome="interview")
        # tr2: 2 applies, 2 callbacks (shortlisted + offer)
        _seed_application(s, u.id, tr2.id, outcome="shortlisted")
        _seed_application(s, u.id, tr2.id, outcome="offer")

        rows = response_rates.by_tailored_resume(s, u.id)

    by_id = {r["tailored_resume_id"]: r for r in rows}
    assert by_id[tr1.id.hex]["applied"] == 3
    assert by_id[tr1.id.hex]["callbacks"] == 1
    assert by_id[tr1.id.hex]["response_rate"] == pytest.approx(1/3, abs=0.01)
    assert by_id[tr2.id.hex]["applied"] == 2
    assert by_id[tr2.id.hex]["callbacks"] == 2
    assert by_id[tr2.id.hex]["response_rate"] == pytest.approx(1.0, abs=0.01)


# ── RED 2: by_archetype rolls up across tailored resumes ────────────────────
def test_by_archetype_rolls_up(session_factory):
    with session_factory() as s:
        # tailored_resume_id is now in the model — create_all added it.
        pass

        u = _seed_user(s)
        tr1 = _seed_tailored(s, u.id, "backend python", "jdh1")
        tr2 = _seed_tailored(s, u.id, "backend python", "jdh2")
        tr3 = _seed_tailored(s, u.id, "ml engineer",    "jdh3")
        _seed_application(s, u.id, tr1.id, outcome="interview")
        _seed_application(s, u.id, tr1.id, outcome=None)
        _seed_application(s, u.id, tr2.id, outcome="offer")
        _seed_application(s, u.id, tr3.id, outcome=None)

        rows = response_rates.by_archetype(s, u.id)

    by_arch = {r["archetype"]: r for r in rows}
    assert by_arch["backend python"]["applied"] == 3
    assert by_arch["backend python"]["callbacks"] == 2
    assert by_arch["ml engineer"]["applied"] == 1
    assert by_arch["ml engineer"]["callbacks"] == 0


# ── RED 3: empty user returns empty list ────────────────────────────────────
def test_empty_user_returns_empty(session_factory):
    with session_factory() as s:
        # tailored_resume_id is now in the model — create_all added it.
        pass
        u = _seed_user(s)
        assert response_rates.by_tailored_resume(s, u.id) == []
        assert response_rates.by_archetype(s, u.id) == []
