"""Tests for backend.services.llm_usage — LLM token/cost capture.

Completes the observability story: every llm_router call records provider,
model, token estimates, and cost into ai_requests (best-effort, never raises,
skipped when there is no user to attribute to). Estimation and cost math are
pure functions so they're testable without providers or a DB.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.services.llm_usage import (
    estimate_tokens, estimate_cost, record_usage, MODEL_COSTS,
)


# ── estimate_tokens (pure) ───────────────────────────────────────────────────

def test_estimate_tokens_empty_is_zero():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


def test_estimate_tokens_roughly_chars_over_four():
    assert estimate_tokens("x" * 400) == 100


def test_estimate_tokens_short_text_at_least_one():
    assert estimate_tokens("hi") == 1


# ── estimate_cost (pure) ─────────────────────────────────────────────────────

def test_known_model_cost_math():
    # pick any configured model and verify the per-1M math
    model, (in_per_m, out_per_m) = next(iter(MODEL_COSTS.items()))
    cost = estimate_cost(model, prompt_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - (in_per_m + out_per_m)) < 1e-9


def test_unknown_model_costs_zero():
    assert estimate_cost("totally-unknown-model", 1000, 1000) == 0.0


def test_local_ollama_models_cost_zero():
    assert estimate_cost("qwen2.5:7b-instruct", 100000, 100000) == 0.0


# ── record_usage (DB sink, best-effort) ──────────────────────────────────────

@pytest.fixture()
def session_factory():
    from backend.models.resume import AIRequest
    eng = create_engine("sqlite://")
    AIRequest.__table__.create(eng)
    return sessionmaker(bind=eng)


def test_record_usage_skips_without_user(session_factory):
    ok = record_usage(provider="groq", model="llama-3.1-8b-instant", role="form_fill",
                      prompt_tokens=10, output_tokens=5, latency_ms=120,
                      user_id=None, session_factory=session_factory)
    assert ok is False


def test_record_usage_writes_row(session_factory):
    ok = record_usage(provider="gemini", model="gemini-2.0-flash", role="writer",
                      prompt_tokens=1000, output_tokens=500, latency_ms=900,
                      user_id="u-123", session_factory=session_factory)
    assert ok is True
    from backend.models.resume import AIRequest
    s = session_factory()
    row = s.query(AIRequest).one()
    assert row.user_id == "u-123"
    assert row.type == "llm:writer"
    assert row.tokens_used == 1500
    assert row.latency_ms == 900
    assert row.input_data["provider"] == "gemini"
    assert row.input_data["model"] == "gemini-2.0-flash"
    assert row.cost_estimate >= 0.0
    s.close()


def test_record_usage_never_raises_on_broken_factory():
    def exploding_factory():
        raise RuntimeError("db down")
    ok = record_usage(provider="groq", model="m", role="form_fill",
                      prompt_tokens=1, output_tokens=1, latency_ms=1,
                      user_id="u-1", session_factory=exploding_factory)
    assert ok is False


# ── llm_router emits usage on success ────────────────────────────────────────

def test_llm_router_records_usage_on_success(monkeypatch):
    import llm_router
    captured = {}

    def fake_record(**kw):
        captured.update(kw)
        return True

    monkeypatch.setattr(llm_router, "_record_usage_safe", fake_record)
    monkeypatch.setattr(llm_router, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(llm_router, "_call_ollama",
                        lambda model, prompt, max_tokens, temperature: "the answer")

    out = llm_router.generate("a prompt of some length here",
                              role="form_fill", config={"user_id": "u-9"})
    assert out == "the answer"
    assert captured["provider"] == "ollama"
    assert captured["role"] == "form_fill"
    assert captured["user_id"] == "u-9"
    assert captured["prompt_tokens"] >= 1
    assert captured["output_tokens"] >= 1


def test_llm_router_usage_failure_does_not_break_generate(monkeypatch):
    import llm_router

    def exploding_record(**kw):
        raise RuntimeError("sink broken")

    monkeypatch.setattr(llm_router, "_record_usage_safe", exploding_record)
    monkeypatch.setattr(llm_router, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(llm_router, "_call_ollama",
                        lambda model, prompt, max_tokens, temperature: "still works")

    assert llm_router.generate("p", role="form_fill", config={"user_id": "u"}) == "still works"
