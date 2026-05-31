"""Tests for backend.services.resume_tailor — Phase B.

Contract:
    resume_tailor.tailor(profile, jd_signature, *, llm=...) -> TailoredResume

Behaviours we MUST guarantee:
    1. Every returned bullet has evidence_in_profile referencing a real
       bullet id in the source profile (hallucination guard).
    2. Bullets whose evidence_in_profile is null or unknown are DROPPED,
       not silently kept.
    3. Header fields (name/email/phone) come straight from profile —
       LLM is not trusted to invent them.
    4. jd_coverage is computed deterministically from the rendered text.
    5. LLM failure → still returns a valid TailoredResume (untailored
       fallback) instead of raising.
"""
from __future__ import annotations

import json
import pytest

from backend.services import resume_tailor
from backend.services.career_schemas import JDSignature, TailoredResume


PROFILE = {
    "name":  "Harsh Raghuwanshi",
    "email": "h@example.com",
    "phone": "+91-9999999999",
    "location": "Bengaluru, IN",
    "skills":  ["python", "fastapi", "postgres"],
    "education": ["B.Tech CSE, Acme Univ, 2024"],
    "experience": [
        {
            "id": "exp_acme",
            "company": "Acme",
            "role": "Software Engineer",
            "bullets": [
                {"id": "b1", "text": "Built FastAPI service serving 5k RPS"},
                {"id": "b2", "text": "Ran Postgres migrations across 12 prod DBs"},
            ],
        },
    ],
}

JD_SIG = JDSignature(
    jd_hash="abcd",
    keywords=["python", "fastapi", "postgres", "aws"],
    must_haves=["python", "fastapi"],
    nice_to_haves=["aws"],
    seniority="mid",
    archetype="backend python",
)


def _stub_llm(payload):
    def _fake(prompt, **kwargs):
        return json.dumps(payload)
    return _fake


# ── RED 1: well-formed LLM output → valid TailoredResume, evidence preserved ──
def test_tailor_returns_tailored_resume_with_valid_evidence():
    llm = _stub_llm({
        "summary": "Backend engineer with FastAPI + Postgres experience.",
        "skills_ordered": ["python", "fastapi", "postgres"],
        "experience": [
            {
                "company": "Acme",
                "role": "Software Engineer",
                "bullets": [
                    {"id": "b1", "text": "Built high-throughput Python FastAPI service",
                     "evidence_in_profile": "b1",
                     "keywords_hit": ["python", "fastapi"]},
                    {"id": "b2", "text": "Owned Postgres migrations across 12 production databases",
                     "evidence_in_profile": "b2",
                     "keywords_hit": ["postgres"]},
                ],
            }
        ],
        "keywords_added": ["python", "fastapi", "postgres"],
    })
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=llm)
    assert isinstance(tr, TailoredResume)
    assert tr.name  == PROFILE["name"]
    assert tr.email == PROFILE["email"]
    assert len(tr.experience) == 1
    assert len(tr.experience[0].bullets) == 2


# ── RED 2: hallucinated bullet (no matching evidence id) is DROPPED ──────────
def test_hallucinated_bullets_are_dropped():
    llm = _stub_llm({
        "summary": "X",
        "skills_ordered": ["python"],
        "experience": [
            {
                "company": "Acme",
                "role": "SWE",
                "bullets": [
                    {"id": "b1", "text": "Built FastAPI service",
                     "evidence_in_profile": "b1", "keywords_hit": ["python"]},
                    # HALLUCINATED — evidence_id "b99" doesn't exist in profile.
                    {"id": "b_evil", "text": "Led 50-person team at Google",
                     "evidence_in_profile": "b99", "keywords_hit": []},
                    # HALLUCINATED — evidence_in_profile is null.
                    {"id": "b_evil2", "text": "Sold company for $1B",
                     "evidence_in_profile": None, "keywords_hit": []},
                ],
            }
        ],
        "keywords_added": ["python"],
    })
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=llm)
    bullet_ids = [b.id for exp in tr.experience for b in exp.bullets]
    assert "b1" in bullet_ids
    assert "b_evil"  not in bullet_ids
    assert "b_evil2" not in bullet_ids
    assert "b_evil"  in tr.dropped_bullets
    assert "b_evil2" in tr.dropped_bullets


# ── RED 3: name/email/phone come from profile, not LLM ───────────────────────
def test_header_fields_come_from_profile_not_llm():
    llm = _stub_llm({
        "summary": "Hi I am Elon Musk",   # adversarial — LLM tries to overwrite
        "name":    "Elon Musk",
        "email":   "elon@x.com",
        "phone":   "000",
        "skills_ordered": [],
        "experience": [],
        "keywords_added": [],
    })
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=llm)
    assert tr.name  == PROFILE["name"]      # NOT "Elon Musk"
    assert tr.email == PROFILE["email"]     # NOT "elon@x.com"
    assert tr.phone == PROFILE["phone"]     # NOT "000"


# ── RED 4: jd_coverage = fraction of must_haves whose lowercase form appears
#          in the rendered resume text ─────────────────────────────────────────
def test_jd_coverage_computed_from_rendered_text():
    llm = _stub_llm({
        "summary": "Python backend engineer.",
        "skills_ordered": ["python"],     # only python is here
        "experience": [
            {"company": "Acme", "role": "SWE",
             "bullets": [
                 {"id": "b1", "text": "Built Python service",
                  "evidence_in_profile": "b1", "keywords_hit": ["python"]}
             ]}
        ],
        "keywords_added": ["python"],
    })
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=llm)
    # JD_SIG.must_haves = ["python", "fastapi"]. Only "python" is rendered.
    assert tr.jd_coverage == pytest.approx(0.5, abs=0.01)


# ── RED 5: LLM failure (None) → safe untailored fallback ────────────────────
def test_llm_failure_returns_safe_fallback():
    def broken_llm(prompt, **kwargs):
        return None
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=broken_llm)
    assert isinstance(tr, TailoredResume)
    assert tr.name == PROFILE["name"]
    # Fallback should still surface SOME experience using verbatim profile bullets.
    assert len(tr.experience) >= 1
    assert len(tr.experience[0].bullets) >= 1
    # Every fallback bullet is its own evidence (verbatim).
    for exp in tr.experience:
        for b in exp.bullets:
            assert b.evidence_in_profile == b.id


# ── RED 6: invalid JSON from LLM → safe untailored fallback ─────────────────
def test_invalid_json_returns_safe_fallback():
    def garbage_llm(prompt, **kwargs):
        return "{ broken json"
    tr = resume_tailor.tailor(PROFILE, JD_SIG, llm=garbage_llm)
    assert isinstance(tr, TailoredResume)
    assert tr.name == PROFILE["name"]
