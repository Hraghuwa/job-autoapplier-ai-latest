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

import json
from typing import Any, Callable, Dict, Optional

from backend.services.untrusted import DATA_RULE, fence, looks_injected

MAX_LEN = 700  # safe for LinkedIn/Greenhouse/Workday "why" textareas

LLMFn = Callable[..., Optional[str]]

_PROMPT = """You are writing ONE short paragraph (3-4 sentences, under 120 words)
for a job application's "why are you a good fit / why this role" field.

STRICT RULES:
- Use ONLY facts from the candidate profile below. Do NOT invent companies,
  titles, skills, metrics, or experience that are not present.
- Reference the role's own language where the profile genuinely supports it.
- First person, warm but professional, no greeting, no signature, no markdown.
- {data_rule}

CANDIDATE PROFILE (the only source of truth about the candidate):
{profile}

JOB (what they are hiring for):
{jd}

Write the paragraph only."""

# Second pass: a reviewer checks the draft against the profile before it is
# submitted under the user's name (drafter→reviewer, as in ai-job-search).
_REVIEW_PROMPT = """You are reviewing a job-application paragraph before it is
submitted. Check every claim about the candidate against the profile.

CANDIDATE PROFILE (the only source of truth):
{profile}

DRAFT:
{draft}

If every claim (companies, titles, skills, metrics, years, experience) is
supported by the profile, return {{"ok": true}}.
Otherwise return {{"ok": false, "revised": "<the paragraph with unsupported
claims removed or softened, same tone, under 120 words>"}}.
Return JSON only."""


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

    if looks_injected(jd_text):
        return static  # posting tries to steer the model — don't let it write for us

    brief = _profile_brief(profile)
    prompt = _PROMPT.format(profile=brief, jd=fence(str(jd_text)[:4000]),
                            data_rule=DATA_RULE.format(tag="job_posting"))
    try:
        out = llm(prompt, role="writer", config=config or {},
                  max_tokens=220, temperature=0.5)
    except Exception:
        return static
    out = (out or "").strip()
    if not out:
        return static
    out = _review(out, brief, llm, config)
    if not out:
        return static
    if len(out) > MAX_LEN:
        out = out[:MAX_LEN].rsplit(" ", 1)[0].rstrip()
    return out


def _review(draft: str, brief: str, llm: LLMFn,
            config: Optional[Dict[str, Any]]) -> str:
    """Reviewer pass. Returns the draft, a revised draft, or "" (→ static note)
    when the reviewer flags unsupported claims but offers no usable fix. A
    reviewer outage keeps the draft: the drafter already ran under strict rules."""
    try:
        raw = llm(_REVIEW_PROMPT.format(profile=brief, draft=draft), role="writer",
                  config=config or {}, max_tokens=260, temperature=0.0) or ""
        verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return draft
    if not isinstance(verdict, dict) or verdict.get("ok") is not False:
        return draft
    return str(verdict.get("revised") or "").strip()


def resolve_cover_note(config: Optional[Dict[str, Any]]) -> str:
    """Applier accessor: per-application tailored note if present, else static."""
    config = config or {}
    tailored = str(config.get("_tailored_cover_note") or "").strip()
    if tailored:
        return tailored
    return str(config.get("cover_letter") or "").strip()
