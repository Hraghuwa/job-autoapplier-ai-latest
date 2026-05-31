"""Tests for backend.services.resume_resolver — Phase E (path resolution).

Contract:
    resolve_resume_path(config, jd_text=None) -> str

When config has a profile + a session_factory + jd_text is provided AND the
build succeeds, the resolver returns the tailored PDF path.
When anything is missing/broken, it falls back to config['resume_path'] —
the agent never fails the upload because of tailoring.
"""
from __future__ import annotations

import json
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.services import resume_resolver
import backend.models  # noqa


@pytest.fixture()
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(eng, expire_on_commit=False)


def _good_jd():
    def _f(p, **kw):
        return json.dumps({"keywords":["python"], "must_haves":["python"],
                           "nice_to_haves":[], "seniority":"mid",
                           "archetype":"backend python", "red_flags":[]})
    return _f
def _good_tailor():
    def _f(p, **kw):
        return json.dumps({"summary":"X","skills_ordered":["python"],
                           "experience":[{"company":"A","role":"E","bullets":[
                               {"id":"b1","text":"Built Python service",
                                "evidence_in_profile":"b1","keywords_hit":["python"]}]}],
                           "keywords_added":["python"]})
    return _f


def _cfg(user_id, session_factory, upload_dir):
    return {
        "user_id":      user_id,
        "resume_path":  "/tmp/static_resume.pdf",
        "profile":      {
            "name":"X","email":"x@x","skills":["python"],
            "experience":[{"id":"e1","company":"A","role":"E",
                          "bullets":[{"id":"b1","text":"Built Python service"}]}],
        },
        "_session_factory": session_factory,
        "_tailored_upload_dir": upload_dir,
        "_jd_llm":       _good_jd(),
        "_tailor_llm":   _good_tailor(),
    }


# ── RED 1: with jd_text + profile → tailored PDF returned ────────────────────
def test_returns_tailored_path_on_happy_path(session_factory, tmp_path):
    upload = str(tmp_path / "tailored")
    cfg = _cfg(uuid.uuid4(), session_factory, upload)
    path = resume_resolver.resolve_resume_path(cfg, jd_text="Python role.")
    assert path.endswith(".pdf")
    assert upload in path
    import os
    assert os.path.exists(path)


# ── RED 2: missing jd_text → fallback to static resume ──────────────────────
def test_no_jd_text_returns_static(session_factory, tmp_path):
    cfg = _cfg(uuid.uuid4(), session_factory, str(tmp_path))
    path = resume_resolver.resolve_resume_path(cfg, jd_text=None)
    assert path == "/tmp/static_resume.pdf"


# ── RED 3: missing user_id → fallback ───────────────────────────────────────
def test_no_user_id_returns_static(session_factory, tmp_path):
    cfg = _cfg(None, session_factory, str(tmp_path))
    cfg["user_id"] = None
    path = resume_resolver.resolve_resume_path(cfg, jd_text="anything")
    assert path == "/tmp/static_resume.pdf"


# ── RED 4: build raises → fallback (resolver never propagates) ──────────────
def test_build_failure_returns_static(session_factory, tmp_path):
    cfg = _cfg(uuid.uuid4(), session_factory, str(tmp_path))
    def boom(*a, **kw): raise RuntimeError("LLM exploded")
    cfg["_jd_llm"] = boom
    cfg["_tailor_llm"] = boom
    # Even if LLM functions raise, jd_analyser.analyse catches — but the
    # build still completes via fallbacks. So we instead break the store
    # by passing an unwritable upload_dir to force a real failure.
    cfg["_tailored_upload_dir"] = "/proc/no/way/this/exists"
    path = resume_resolver.resolve_resume_path(cfg, jd_text="x")
    # On error we must fall back to static — never crash the apply pipeline.
    assert path == "/tmp/static_resume.pdf"
