"""should_apply — the pre-apply gate the appliers call (PLAN §1 match gate).

Glues jd_analyser (JD text → signature) to fit_scorer (signature + profile →
decision). One call an applier makes the moment it has the JD text and is about
to spend an application:

    from backend.services.apply_decision import should_apply
    d = should_apply(config, jd_text=jd, title=job_title)
    if not d.apply:
        print(f"⏭ Skipping ({d.score}/100): {d.reasons[-1]}")
        continue

Design:
  * fail-OPEN — missing context (no JD text), disabled gate, or any internal
    error returns apply=True, so the gate can only ever *prevent waste*, never
    block working flows. A scorer bug degrades to today's behaviour.
  * floor comes from config['match_threshold'] (the user's onboarding setting),
    else fit_scorer.DEFAULT_FLOOR.
  * config['_jd_llm'] lets tests inject a fake analyser; production uses the
    real llm_router via jd_analyser's default. jd_analyser caches nothing here,
    but tailored_resume_store reuses the same signature path, so the LLM cost
    of gating ≈ the cost of tailoring we'd have paid anyway — and a SKIP saves
    the whole tailor+render+apply spend.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.fit_scorer import score_fit, FitDecision, DEFAULT_FLOOR


def should_apply(config: Dict[str, Any], *, jd_text: Optional[str],
                 title: Optional[str] = None) -> FitDecision:
    config = config or {}
    if config.get("fit_gate_enabled") is False:
        return FitDecision(score=100, apply=True, vetoed=False,
                           reasons=["Fit gate disabled in config — applying."],
                           components={})

    if not jd_text or not str(jd_text).strip():
        return FitDecision(score=DEFAULT_FLOOR, apply=True, vetoed=False,
                           reasons=["No JD context available — applying (fail-open)."],
                           components={})

    try:
        from backend.services import jd_analyser
        sig = jd_analyser.analyse(jd_text, llm=config.get("_jd_llm"), config=config)
    except Exception:
        return FitDecision(score=DEFAULT_FLOOR, apply=True, vetoed=False,
                           reasons=["JD analysis failed — applying (fail-open)."],
                           components={})

    try:
        floor = int(config.get("match_threshold") or DEFAULT_FLOOR)
    except (TypeError, ValueError):
        floor = DEFAULT_FLOOR

    profile = config.get("profile") or {}
    return score_fit(sig, profile, title=title, floor=floor)
