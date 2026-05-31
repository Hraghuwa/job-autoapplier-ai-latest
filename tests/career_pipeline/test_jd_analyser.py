"""Tests for backend.services.jd_analyser — Phase A of the career pipeline.

Contract under test:
    jd_analyser.analyse(jd_text, *, llm=...) -> JDSignature
    JDSignature is a pydantic model with: keywords, must_haves, nice_to_haves,
        seniority, archetype, red_flags, jd_hash.

Tests inject a fake LLM so they don't burn real API tokens or depend on
Ollama running on CI.
"""
from __future__ import annotations

import json
import pytest

from backend.services import jd_analyser
from backend.services.career_schemas import JDSignature


SAMPLE_JD = """
Senior Python Engineer — Acme AI
We're hiring a senior backend engineer to build agentic systems.
Required: 5+ years Python, FastAPI, Postgres, AWS, async I/O.
Nice to have: Rust, LLM fine-tuning, vector databases.
Red flags: must work 6 days/week, unpaid trial period.
"""


def _fake_llm(response_obj):
    """Return a stub `llm` callable that always emits the given JSON object."""
    def _fake(prompt, **kwargs):
        return json.dumps(response_obj)
    return _fake


# ── RED 1: smoke — analyse returns a JDSignature on a real-looking JD ────────
def test_analyse_returns_jd_signature_for_well_formed_response():
    llm = _fake_llm({
        "keywords":      ["python", "fastapi", "postgres", "aws", "async"],
        "must_haves":    ["python", "fastapi", "5+ years"],
        "nice_to_haves": ["rust", "llm fine-tuning"],
        "seniority":     "senior",
        "archetype":     "backend python",
        "red_flags":     ["unpaid trial period", "6 days/week"],
    })
    sig = jd_analyser.analyse(SAMPLE_JD, llm=llm)
    assert isinstance(sig, JDSignature)
    assert "python" in sig.keywords
    assert sig.seniority == "senior"
    assert sig.archetype == "backend python"


# ── RED 2: jd_hash is deterministic for the same JD text ────────────────────
def test_jd_hash_is_deterministic():
    llm = _fake_llm({
        "keywords": ["x"], "must_haves": [], "nice_to_haves": [],
        "seniority": "mid", "archetype": "x", "red_flags": [],
    })
    sig1 = jd_analyser.analyse(SAMPLE_JD, llm=llm)
    sig2 = jd_analyser.analyse(SAMPLE_JD, llm=llm)
    assert sig1.jd_hash == sig2.jd_hash
    assert len(sig1.jd_hash) >= 16   # SHA-ish


# ── RED 3: hallucination guard drops must_haves not in JD text ──────────────
def test_must_haves_not_in_jd_text_are_dropped():
    # Model hallucinates "kubernetes" — not present in the JD.
    llm = _fake_llm({
        "keywords":      ["python", "kubernetes"],
        "must_haves":    ["python", "kubernetes"],   # kubernetes is fabricated
        "nice_to_haves": [],
        "seniority":     "mid",
        "archetype":     "backend",
        "red_flags":     [],
    })
    sig = jd_analyser.analyse(SAMPLE_JD, llm=llm)
    assert "python" in sig.must_haves
    assert "kubernetes" not in sig.must_haves   # MUST be dropped


# ── RED 4: bad LLM output → safe empty signature, no exception ──────────────
def test_invalid_llm_output_returns_safe_empty_signature():
    def broken_llm(prompt, **kwargs):
        return "not json at all <<<>>>"
    sig = jd_analyser.analyse(SAMPLE_JD, llm=broken_llm)
    assert isinstance(sig, JDSignature)
    assert sig.keywords == []
    assert sig.archetype == "unknown"
    assert sig.jd_hash   # still hashes the input text


# ── RED 5: LLM returns None (provider chain fully failed) ───────────────────
def test_none_from_llm_returns_safe_empty_signature():
    def none_llm(prompt, **kwargs):
        return None
    sig = jd_analyser.analyse(SAMPLE_JD, llm=none_llm)
    assert isinstance(sig, JDSignature)
    assert sig.keywords == []


# ── RED 6: empty JD → empty signature, no crash ─────────────────────────────
def test_empty_jd_text():
    llm = _fake_llm({"keywords": [], "must_haves": [], "nice_to_haves": [],
                     "seniority": "unknown", "archetype": "unknown", "red_flags": []})
    sig = jd_analyser.analyse("", llm=llm)
    assert sig.keywords == []
