"""LLM token/cost capture — completes the observability layer (audit §6c).

llm_router.generate calls record_usage after every successful provider call so
ai_requests accumulates per-call provider/model/token/cost data. Design rules:

  * NEVER raises — a broken DB must not break form-filling.
  * Skips when there is no user_id (Layer-A CLI runs; ai_requests.user_id is
    NOT NULL and the local CLI is free anyway).
  * Token counts are ESTIMATES (~4 chars/token). Provider usage metadata varies
    wildly across Ollama/Groq/Gemini and two SDK generations; a consistent
    estimator beats three fragile parsers. Costs are therefore approximate —
    good for trend lines and leak detection, not invoicing.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# USD per 1M tokens (input, output). Local models are free. Update as pricing
# moves; unknown models cost 0 rather than guessing.
MODEL_COSTS = {
    "llama-3.1-8b-instant":    (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "gemini-2.0-flash":        (0.10, 0.40),
    "gemini-1.5-flash":        (0.075, 0.30),
}


def estimate_tokens(text: Optional[str]) -> int:
    """~4 chars/token heuristic. 0 for empty, at least 1 for any content."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_cost(model: str, prompt_tokens: int, output_tokens: int) -> float:
    """USD estimate; 0.0 for local/unknown models."""
    rates = MODEL_COSTS.get(model)
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    return (prompt_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def _default_session_factory():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.config import settings
    url = settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    eng = create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})
    return sessionmaker(bind=eng)


def record_usage(
    *,
    provider: str,
    model: str,
    role: str,
    prompt_tokens: int,
    output_tokens: int,
    latency_ms: int,
    user_id: Optional[str],
    session_factory: Optional[Callable] = None,
) -> bool:
    """Write one ai_requests row. Returns True on write, False on skip/failure.

    Never raises — callers are inside the apply hot path.
    """
    if not user_id:
        return False
    try:
        from backend.models.resume import AIRequest
        factory = session_factory or _default_session_factory()
        session = factory()
        try:
            session.add(AIRequest(
                user_id=str(user_id),
                type=f"llm:{role}",
                input_data={
                    "provider": provider,
                    "model": model,
                    "prompt_tokens": int(prompt_tokens),
                    "output_tokens": int(output_tokens),
                },
                output_data=None,
                latency_ms=int(latency_ms),
                tokens_used=int(prompt_tokens) + int(output_tokens),
                cost_estimate=estimate_cost(model, prompt_tokens, output_tokens),
            ))
            session.commit()
            return True
        finally:
            session.close()
    except Exception as e:
        logger.debug("llm_usage: capture skipped (%s)", e)
        return False
