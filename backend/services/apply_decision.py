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

    profile = dict(config.get("profile") or {})
    profile["_target_seniority"] = config.get("target_seniority") or ""
    decision = score_fit(sig, profile, title=title, floor=floor,
                         archetype_rates=config.get("_archetype_rates"))
    # report_job() attaches this to the Application row for the job being applied to.
    config["_last_fit"] = {"score": decision.score, "missing": decision.missing}
    return decision


JOB_MARKER = "JOBAGENT_JOB "


def report_job(config: Dict[str, Any], status: str, *, title: str = "", company: str = "",
               url: str = "", jd_text: Optional[str] = None) -> None:
    """Print one machine-readable line the worker turns into a full Application
    row (JD, fit score, missing skills, cover note, tailored resume).

    status: "applied" (submitted) or "prepared" (form filled, left for the user
    to submit). Call it BEFORE the human-readable success line: once the worker
    has seen a marker it stops counting the legacy text lines, so nothing is
    double-counted. Never raises — reporting must not break an apply."""
    import json
    try:
        fit = config.get("_last_fit") or {}
        rec = {
            "status": status, "title": (title or "")[:255], "company": (company or "")[:255],
            "url": url or "",
            "jd_text": (jd_text or config.get("current_jd_text") or config.get("_current_jd") or "")[:8000],
            "match_score": fit.get("score"), "missing_skills": fit.get("missing") or [],
            "cover_note_used": config.get("_tailored_cover_note") or None,
            "tailored_resume_id": config.get("_tailored_resume_id") or None,
            # Questions the form asked that no saved answer covered → the user's
            # answer bank (Claude fills it so the next mission answers them).
            "questions": [str(q)[:300] for q in (config.get("_unanswered") or []) if q][:30],
        }
        print(JOB_MARKER + json.dumps(rec, ensure_ascii=False), flush=True)
    except Exception:
        pass
    finally:
        # Per-job context must not leak into the next job's record.
        for k in ("_last_fit", "_tailored_cover_note", "_tailored_resume_id", "_unanswered"):
            config.pop(k, None)


def rate_ok(config: Dict[str, Any], platform: str) -> bool:
    """Call BEFORE clicking Apply. False (and prints why) when the per-platform
    safety cap, the consecutive-failure pause, or the plan's daily cap is hit.

    The plan cap also counts today's applications from the DB (the worker sets
    config["_applied_today"]) plus this run's, so it holds even when Redis is
    down and the in-memory limiter starts empty in every phase subprocess."""
    cap = config.get("plan_apply_limit")
    if cap is not None and config.get("_applied_today", 0) + config.get("_run_handled", 0) >= cap:
        print(f"  🛑 Rate limit reached: plan daily apply limit ({cap})")
        return False
    try:
        from backend.services.rate_limits import default_limiter
        ok, reason = default_limiter.can_apply(str(config.get("user_id", "")), platform, total_cap=cap)
    except Exception:
        return True  # limiter unavailable — the DB-based plan cap above still applies
    if not ok:
        print(f"  🛑 Rate limit reached: {reason}")
    return ok


def rate_register(config: Dict[str, Any], platform: str, success: bool = True) -> None:
    """Record one application attempt (applied or prepared) after it happens."""
    if success:
        config["_run_handled"] = config.get("_run_handled", 0) + 1
    try:
        from backend.services.rate_limits import default_limiter
        uid = str(config.get("user_id", ""))
        if success:
            default_limiter.register_apply(uid, platform)
            default_limiter.register_success(uid, platform)
        else:
            default_limiter.register_failure(uid, platform)
    except Exception:
        pass
