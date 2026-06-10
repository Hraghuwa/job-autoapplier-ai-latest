"""JD-aware cover / "why this role" note (PLAN: auto-personalised outreach).

Every motivation/cover-letter field in the appliers was filled with the same
static config['cover_letter'] regardless of the job. generate() writes a short
note that references the JD's language using ONLY facts the candidate actually
has (skills + experience summary from the profile), so it reads as written-for-
this-job without inventing experience.

Contract:
  * STRICT fail-open — no JD text, empty/failed LLM, or any error returns the
    static note (config['cover_letter'] → profile['cover_letter'] → ""). A
    cover-note bug must never degrade an application below today's behaviour.
  * length-capped (most "why" textareas truncate); single paragraph.
  * pure: llm is injectable; production uses llm_router.generate (writer role).

resolve_cover_note(config) is what the appliers call at fill time: prefer a
per-application _tailored_cover_note (generated once when JD is captured) else
the static note.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

MAX_LEN = 700  # safe for LinkedIn/Greenhouse/Workday "why" textareas

LLMFn = Callable[..., Optional[str]]

_PROMPT = """You are writing ONE short paragraph (3-4 sentences, under 120 words)
for a job application's "why are you a good fit / why this role" field.

STRICT RULES:
- Use ONLY facts from the candidate profile below. Do NOT invent companies,
  titles, skills, metrics, or experience that are not present.
- Reference the role's own language where the profile genuinely supports it.
- First person, warm but professional, no greeting, no signature, no markdown.

CANDIDATE PROFILE (the only source of truth about the candidate):
{profile}

JOB (what they are hiring for):
{jd}

Write the paragraph only."""


def _static(profile: Optional[Dict[str, Any]], config: Optional[Dict[str, Any]]) -> str:
    config = config or {}
    profile = profile if isinstance(profile, dict) else {}
    return (str(config.get("cover_letter") or "").strip()
            or str(profile.get("cover_letter") or "").strip())


def _profile_brief(profile: Dict[str, Any]) -> str:
    keys = ("full_name", "skills", "experience_summary", "experience",
            "current_role", "summary", "education")
    parts = []
    for k in keys:
        v = profile.get(k)
        if isinstance(v, (list, dict)):
            v = str(v)
        if v:
            parts.append(f"{k}: {str(v)[:400]}")
    return "\n".join(parts)[:2000]


def generate(profile: Optional[Dict[str, Any]], *, jd_text: Optional[str],
             config: Optional[Dict[str, Any]] = None,
             llm: Optional[LLMFn] = None) -> str:
    """Return a JD-tailored note, or the static note on any failure."""
    static = _static(profile, config)
    if not jd_text or not str(jd_text).strip():
        return static  # no context → don't even call the model
    if not isinstance(profile, dict) or not profile:
        return static
    if llm is None:
        try:
            from llm_router import generate as _gen
            llm = _gen
        except Exception:
            return static

    prompt = _PROMPT.format(profile=_profile_brief(profile), jd=str(jd_text)[:4000])
    try:
        out = llm(prompt, role="writer", config=config or {},
                  max_tokens=220, temperature=0.5)
    except Exception:
        return static
    out = (out or "").strip()
    if not out:
        return static
    if len(out) > MAX_LEN:
        out = out[:MAX_LEN].rsplit(" ", 1)[0].rstrip()
    return out


def resolve_cover_note(config: Optional[Dict[str, Any]]) -> str:
    """Applier accessor: per-application tailored note if present, else static."""
    config = config or {}
    tailored = str(config.get("_tailored_cover_note") or "").strip()
    if tailored:
        return tailored
    return str(config.get("cover_letter") or "").strip()
