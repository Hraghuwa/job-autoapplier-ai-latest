"""Phase B — Resume tailor.

Reads a user profile + JD signature, asks the writer-role LLM for a tailored
version, then runs a strict hallucination guard before returning. Any bullet
whose `evidence_in_profile` does NOT match a real profile bullet id is
DROPPED, recorded in `dropped_bullets`, and never reaches Phase C.

Header fields (name/email/phone) are taken straight from the profile —
the LLM is never allowed to overwrite them.

Model used:
    role="writer"  →  Ollama Qwen2.5-14B  →  Gemini Flash  →  Groq Llama-3.3-70B
    Writer-role because we need careful prose with low hallucination, and
    14B is the sweet spot for clean bullet rewrites that survive the guard.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

from backend.services.career_schemas import (
    JDSignature, TailoredBullet, TailoredExperience, TailoredResume,
)

# Make repo-root llm_router importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

LLMFn = Callable[..., Optional[str]]


def _default_llm() -> LLMFn:
    from llm_router import generate as _generate
    return _generate


def _as_str_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,;\n]", value) if p.strip()]
        return parts or [value.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _experience_items(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Accept both test shape (`experience`) and app shape (`experiences`)."""
    raw = profile.get("experience")
    if not isinstance(raw, list):
        raw = profile.get("experiences")
    if not isinstance(raw, list):
        raw = []

    out: List[Dict[str, Any]] = []
    for idx, exp in enumerate(raw):
        if isinstance(exp, str):
            text = exp.strip()
            if text:
                out.append({
                    "company": "",
                    "role": "",
                    "bullets": [{"id": f"b{idx + 1}", "text": text}],
                })
            continue
        if not isinstance(exp, dict):
            continue
        bullets = exp.get("bullets")
        if not isinstance(bullets, list):
            desc = exp.get("description") or exp.get("summary") or exp.get("details")
            bullets = [{"id": f"b{idx + 1}", "text": str(desc)}] if desc else []
        cleaned = []
        for b_idx, b in enumerate(bullets):
            if isinstance(b, str):
                cleaned.append({"id": f"b{idx + 1}_{b_idx + 1}", "text": b})
            elif isinstance(b, dict):
                text = b.get("text") or b.get("description") or b.get("summary")
                if text:
                    cleaned.append({
                        **b,
                        "id": str(b.get("id") or f"b{idx + 1}_{b_idx + 1}"),
                        "text": str(text),
                    })
        out.append({
            **exp,
            "company": exp.get("company") or "",
            "role": exp.get("role") or exp.get("title") or "",
            "bullets": cleaned,
        })
    return out


# ── Prompt ──────────────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """You are a careful resume editor for a job application agent.

Rewrite the candidate's bullets to maximise relevance to the JD WITHOUT
inventing any experience the candidate doesn't have.

ABSOLUTE RULES:
- For EACH bullet you output, you MUST set "evidence_in_profile" to the id
  of the source bullet from the profile below. If a rewrite would require
  experience not in the profile, OMIT that bullet entirely.
- NEVER add a new company, role, or skill that is not in the profile.
- Use ACTIVE voice and quantified outcomes where the source bullet allows.
- Keep length ≤ 25 words per bullet.

PROFILE (source of truth):
{profile_json}

JD must-haves (try to surface where the profile genuinely supports it):
{must_haves}

JD nice-to-haves:
{nice_to_haves}

JD keywords:
{keywords}

Return ONLY a JSON object with this exact shape (no markdown, no commentary):
{{
  "summary": "2-sentence professional summary",
  "skills_ordered": ["lowercase skills in priority order"],
  "experience": [
    {{
      "company": "...",
      "role": "...",
      "bullets": [
        {{
          "id": "stable id like b1",
          "text": "Rewritten bullet text",
          "evidence_in_profile": "id from profile experience[].bullets[].id",
          "keywords_hit": ["python", "fastapi"]
        }}
      ]
    }}
  ],
  "keywords_added": ["python", "fastapi"]
}}
"""


def _profile_bullet_ids(profile: Dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for exp in _experience_items(profile):
        for b in exp.get("bullets") or []:
            bid = b.get("id")
            if bid:
                ids.add(str(bid))
    return ids


def _strip_code_fence(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.lstrip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def _coverage(rendered_text: str, must_haves: List[str]) -> float:
    if not must_haves:
        return 1.0
    haystack = rendered_text.lower()
    hits = sum(1 for m in must_haves if (m or "").strip().lower() in haystack)
    return hits / len(must_haves)


def _fallback_untailored(profile: Dict[str, Any], jd_sig: JDSignature) -> TailoredResume:
    """When the LLM is unavailable or output is unusable, build a resume
    directly from the profile — every bullet uses itself as evidence so the
    guard cannot reject any of them. This is the 'always works' floor."""
    experience: List[TailoredExperience] = []
    rendered_chunks: List[str] = []
    for exp in _experience_items(profile):
        bullets: List[TailoredBullet] = []
        for b in exp.get("bullets") or []:
            bid = str(b.get("id") or "")
            text = str(b.get("text") or "").strip()
            if not bid or not text:
                continue
            bullets.append(TailoredBullet(
                id=bid, text=text, evidence_in_profile=bid, keywords_hit=[],
            ))
            rendered_chunks.append(text)
        if bullets:
            experience.append(TailoredExperience(
                company=str(exp.get("company") or ""),
                role=str(exp.get("role") or ""),
                bullets=bullets,
            ))
    skills = _as_str_list(profile.get("skills"))
    education = _as_str_list(profile.get("education"))
    rendered = " ".join(rendered_chunks + skills)
    return TailoredResume(
        name      = str(profile.get("name") or profile.get("full_name") or ""),
        email     = str(profile.get("email") or ""),
        phone     = profile.get("phone"),
        location  = profile.get("location"),
        summary   = (profile.get("summary") or
                     "Engineer with hands-on experience across the stack.").strip()[:400],
        skills    = skills[:20],
        experience= experience,
        education = education,
        jd_coverage = _coverage(rendered, jd_sig.must_haves),
        dropped_bullets = [],
    )


def tailor(
    profile: Dict[str, Any],
    jd_sig: JDSignature,
    *,
    llm: Optional[LLMFn] = None,
    config: Optional[Dict[str, Any]] = None,
) -> TailoredResume:
    """Produce a TailoredResume that is guaranteed safe to render to PDF.

    The function never raises. Header fields always come from `profile`,
    not the LLM. Hallucinated bullets are dropped, not rewritten.
    """
    if llm is None:
        llm = _default_llm()

    valid_ids = _profile_bullet_ids(profile)
    prompt_profile = {**profile, "experience": _experience_items(profile)}

    prompt = _PROMPT_TEMPLATE.format(
        profile_json   = json.dumps(prompt_profile, default=str)[:6000],
        must_haves     = ", ".join(jd_sig.must_haves) or "(none)",
        nice_to_haves  = ", ".join(jd_sig.nice_to_haves) or "(none)",
        keywords       = ", ".join(jd_sig.keywords) or "(none)",
    )

    try:
        raw = llm(prompt, role="writer", config=config or {},
                  max_tokens=2000, temperature=0.3)
    except Exception:
        return _fallback_untailored(profile, jd_sig)

    if not raw:
        return _fallback_untailored(profile, jd_sig)

    try:
        data = json.loads(_strip_code_fence(raw))
    except Exception:
        return _fallback_untailored(profile, jd_sig)

    if not isinstance(data, dict):
        return _fallback_untailored(profile, jd_sig)

    # ── Build experience list with hallucination guard ──────────────────────
    dropped: List[str] = []
    experience_out: List[TailoredExperience] = []
    rendered_chunks: List[str] = []

    for exp in data.get("experience") or []:
        if not isinstance(exp, dict):
            continue
        kept_bullets: List[TailoredBullet] = []
        for b in exp.get("bullets") or []:
            if not isinstance(b, dict):
                continue
            bid    = str(b.get("id") or "")
            text   = str(b.get("text") or "").strip()
            ev     = b.get("evidence_in_profile")
            ev_str = str(ev) if ev is not None else ""
            khits  = [k for k in (b.get("keywords_hit") or []) if isinstance(k, str)]
            if not text or not ev_str or ev_str not in valid_ids:
                # Hallucination — drop and record.
                if bid:
                    dropped.append(bid)
                continue
            kept_bullets.append(TailoredBullet(
                id=bid or ev_str, text=text[:300],
                evidence_in_profile=ev_str, keywords_hit=khits,
            ))
            rendered_chunks.append(text)
        if kept_bullets:
            experience_out.append(TailoredExperience(
                company=str(exp.get("company") or ""),
                role=str(exp.get("role") or ""),
                bullets=kept_bullets,
            ))

    # If the guard wiped out *all* experience, fall back rather than ship empty.
    if not experience_out:
        fb = _fallback_untailored(profile, jd_sig)
        fb.dropped_bullets = dropped
        return fb

    profile_skills = _as_str_list(profile.get("skills"))
    profile_education = _as_str_list(profile.get("education"))
    skills_ordered = [s for s in (data.get("skills_ordered") or []) if isinstance(s, str)]
    rendered_chunks.extend(skills_ordered)
    rendered_text = " ".join(rendered_chunks)

    return TailoredResume(
        # Header fields — ALWAYS from profile, never from LLM.
        name     = str(profile.get("name") or profile.get("full_name") or ""),
        email    = str(profile.get("email") or ""),
        phone    = profile.get("phone"),
        location = profile.get("location"),

        summary  = str(data.get("summary") or "").strip()[:400] or
                   "Engineer with hands-on experience across the stack.",
        skills   = skills_ordered[:20] or profile_skills[:20],
        experience      = experience_out,
        education       = profile_education,
        keywords_added  = [k for k in (data.get("keywords_added") or []) if isinstance(k, str)][:20],
        jd_coverage     = _coverage(rendered_text, jd_sig.must_haves),
        dropped_bullets = dropped,
    )
