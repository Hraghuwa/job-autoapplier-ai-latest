"""Tests for backend.services.tailored_resume_store — Phase D.

Contract:
    store.get_or_build(user_id, profile, jd_text, *, jd_llm, tailor_llm) -> StoreEntry
    store.get(user_id, jd_text) -> StoreEntry | None

Guarantees:
    1. First call writes a row + PDF on disk; second call reuses it (idempotent).
    2. PDF path returned actually exists on disk and is a valid PDF.
    3. Different JDs for the same user produce different cache entries.
    4. Bumping profile_version invalidates the cache (re-builds).
    5. Cache key is the (user_id, jd_hash, profile_version) tuple.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.services import tailored_resume_store as store
import backend.models  # noqa — register all models


@pytest.fixture()
def session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    eng = create_engine(db_url, future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(eng, expire_on_commit=False)


@pytest.fixture()
def upload_dir(tmp_path):
    d = tmp_path / "tailored"
    d.mkdir()
    return str(d)


PROFILE = {
    "name": "Harsh", "email": "h@x", "phone": "+91", "location": "BLR",
    "skills": ["python", "fastapi"],
    "education": ["B.Tech"],
    "experience": [
        {"id": "exp_a", "company": "Acme", "role": "SWE",
         "bullets": [{"id": "b1", "text": "Built FastAPI service"}]}
    ],
}


def _jd_llm(payload):
    def _f(prompt, **kw): return json.dumps(payload)
    return _f


def _good_jd_llm():
    return _jd_llm({
        "keywords": ["python", "fastapi"], "must_haves": ["python", "fastapi"],
        "nice_to_haves": [], "seniority": "mid", "archetype": "backend python",
        "red_flags": [],
    })


def _good_tailor_llm():
    def _f(prompt, **kw):
        return json.dumps({
            "summary": "Backend engineer.",
            "skills_ordered": ["python", "fastapi"],
            "experience": [{
                "company": "Acme", "role": "SWE",
                "bullets": [
                    {"id": "b1", "text": "Built FastAPI service at scale",
                     "evidence_in_profile": "b1", "keywords_hit": ["python", "fastapi"]}
                ],
            }],
            "keywords_added": ["python", "fastapi"],
        })
    return _f


JD_A = "Senior Python Engineer. FastAPI required."
JD_B = "Junior Data Analyst. SQL required."


# ── RED 1: first call builds + writes PDF ───────────────────────────────────
def test_get_or_build_writes_pdf_and_db_row(session_factory, upload_dir):
    uid = uuid.uuid4()
    with session_factory() as sess:
        entry = store.get_or_build(
            sess, uid, PROFILE, JD_A,
            jd_llm=_good_jd_llm(), tailor_llm=_good_tailor_llm(),
            upload_dir=upload_dir,
        )
    assert os.path.exists(entry.pdf_path)
    with open(entry.pdf_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


# ── RED 2: second call with same JD reuses cached entry ─────────────────────
def test_second_call_is_idempotent(session_factory, upload_dir):
    uid = uuid.uuid4()
    # Use a counting LLM to PROVE we don't re-call it on second get
    calls = {"jd": 0, "tailor": 0}
    def counting_jd(prompt, **kw):
        calls["jd"] += 1
        return _good_jd_llm()(prompt, **kw)
    def counting_tailor(prompt, **kw):
        calls["tailor"] += 1
        return _good_tailor_llm()(prompt, **kw)

    with session_factory() as sess:
        e1 = store.get_or_build(sess, uid, PROFILE, JD_A,
                                jd_llm=counting_jd, tailor_llm=counting_tailor,
                                upload_dir=upload_dir)
        e2 = store.get_or_build(sess, uid, PROFILE, JD_A,
                                jd_llm=counting_jd, tailor_llm=counting_tailor,
                                upload_dir=upload_dir)
    assert e1.id == e2.id
    assert e1.pdf_path == e2.pdf_path
    assert calls["jd"] == 1   # NOT 2 — second call hit cache
    assert calls["tailor"] == 1


# ── RED 3: different JDs → different cache entries ──────────────────────────
def test_different_jd_text_gives_different_entries(session_factory, upload_dir):
    uid = uuid.uuid4()
    with session_factory() as sess:
        e1 = store.get_or_build(sess, uid, PROFILE, JD_A,
                                jd_llm=_good_jd_llm(), tailor_llm=_good_tailor_llm(),
                                upload_dir=upload_dir)
        e2 = store.get_or_build(sess, uid, PROFILE, JD_B,
                                jd_llm=_good_jd_llm(), tailor_llm=_good_tailor_llm(),
                                upload_dir=upload_dir)
    assert e1.jd_hash != e2.jd_hash
    assert e1.pdf_path != e2.pdf_path


# ── RED 4: bumping profile_version forces re-build ──────────────────────────
def test_bumping_profile_version_invalidates_cache(session_factory, upload_dir):
    uid = uuid.uuid4()
    p1 = dict(PROFILE, _profile_version=1)
    p2 = dict(PROFILE, _profile_version=2)
    with session_factory() as sess:
        e1 = store.get_or_build(sess, uid, p1, JD_A,
                                jd_llm=_good_jd_llm(), tailor_llm=_good_tailor_llm(),
                                upload_dir=upload_dir)
        e2 = store.get_or_build(sess, uid, p2, JD_A,
                                jd_llm=_good_jd_llm(), tailor_llm=_good_tailor_llm(),
                                upload_dir=upload_dir)
    assert e1.id != e2.id
    assert e1.profile_ver == 1
    assert e2.profile_ver == 2
