"""Career-Ops — AI filter/tailoring layer ported from career-ops-main.

Provides: offer evaluation (A–F scoring + G legitimacy), CV tailoring per JD,
interview story bank CRUD, negotiation script generation, and portal scanning
summarisation. All endpoints are user-scoped.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.profile import UserProfile

router = APIRouter()

_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if _GEMINI_KEY:
    genai.configure(api_key=_GEMINI_KEY)

# In-memory story bank + negotiation cache (per-user). Survives process lifetime
# only — good enough for the v1 slice, migrate to DB in follow-up.
_STORY_BANK: Dict[str, List[Dict[str, Any]]] = {}
_EVALUATIONS: Dict[str, List[Dict[str, Any]]] = {}


def _model():
    if not _GEMINI_KEY:
        raise HTTPException(503, "AI engine not configured")
    return genai.GenerativeModel("gemini-1.5-flash")


def _parse_json(text: str) -> Dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip("` \n")
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        t = m.group(0)
    return json.loads(t)


async def _cv_summary(db: AsyncSession, user: User) -> str:
    """Pull a compact textual CV summary from the user's profile (extracted_data JSON)."""
    res = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    p: Optional[UserProfile] = res.scalar_one_or_none()
    if not p or not p.extracted_data:
        return ""
    d = p.extracted_data or {}
    parts: List[str] = []
    for k in ("name", "email", "phone", "location", "summary"):
        if d.get(k):
            parts.append(f"{k.title()}: {d[k]}")
    if d.get("skills"):
        parts.append(f"Skills: {', '.join(d['skills']) if isinstance(d['skills'], list) else d['skills']}")
    if d.get("experience"):
        parts.append(f"Experience: {json.dumps(d['experience'])[:1800]}")
    if d.get("education"):
        parts.append(f"Education: {json.dumps(d['education'])[:700]}")
    if d.get("certifications"):
        parts.append(f"Certifications: {json.dumps(d['certifications'])[:400]}")
    return "\n".join(parts)


# ── Schemas ───────────────────────────────────────────────────────────────────

class EvaluateBody(BaseModel):
    jd_text: str = Field(..., min_length=40, description="Job description text")
    url: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None


class TailorCVBody(BaseModel):
    jd_text: str
    role: Optional[str] = None
    company: Optional[str] = None


class StoryIn(BaseModel):
    title: str
    situation: str
    task: str
    action: str
    result: str
    reflection: Optional[str] = ""
    tags: List[str] = []


class NegotiationBody(BaseModel):
    company: str
    role: str
    current_offer: Optional[str] = ""
    target: Optional[str] = ""
    competing_offers: Optional[str] = ""
    geo_context: Optional[str] = ""


class ScanBody(BaseModel):
    query: str = Field(..., description="Keywords / archetype e.g. 'applied AI, LLM ops'")
    companies: List[str] = Field(default_factory=list)


# ── Evaluation (Blocks A–G) ──────────────────────────────────────────────────

EVAL_PROMPT = """You are career-ops, an A–F offer evaluator with a G (legitimacy) block.
Return ONLY valid JSON. Be specific, no placeholders. Scores 0-5 (one decimal ok).

Input:
CANDIDATE_CV:
{cv}

JOB_DESCRIPTION:
{jd}

ROLE_HINT: {role}
COMPANY_HINT: {company}

Return this exact JSON shape:
{{
  "overall_score": 0.0,
  "recommendation": "apply|tailor-first|skip",
  "archetype": "FDE|SA|PM|LLMOps|Agentic|Transformation|Other",
  "tldr": "one sentence",
  "blocks": {{
    "A_role_summary": {{"domain": "", "function": "", "seniority": "", "remote": "", "tldr": ""}},
    "B_cv_match": {{"score": 0.0, "matched": ["bullet..."], "gaps": [{{"gap": "", "blocker": false, "mitigation": ""}}]}},
    "C_level_strategy": {{"detected_level": "", "candidate_level": "", "sell_senior_lines": [""], "downlevel_plan": ""}},
    "D_comp_demand": {{"salary_range_usd": "", "demand_trend": "", "notes": ""}},
    "E_personalization": {{"cv_changes": [""], "linkedin_changes": [""]}},
    "F_interview_prep": {{"stories": [{{"title": "", "jd_requirement": "", "S": "", "T": "", "A": "", "R": "", "reflection": ""}}], "red_flag_questions": [""]}},
    "G_legitimacy": {{"tier": "A|B|C|D", "signals": [""], "rationale": ""}}
  }},
  "weighted_scores": {{"fit": 0.0, "comp": 0.0, "growth": 0.0, "remote": 0.0, "mission": 0.0, "tech": 0.0, "team": 0.0, "risk": 0.0, "stability": 0.0, "negotiation_leverage": 0.0}}
}}
If CANDIDATE_CV is empty, still produce a JD-only evaluation and set B_cv_match.score to 0 with gaps noting missing CV.
"""


@router.post("/evaluate")
async def evaluate_offer(
    body: EvaluateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run 7-block (A–G) career-ops evaluation on a job description."""
    cv = await _cv_summary(db, user)
    prompt = EVAL_PROMPT.format(
        cv=cv[:5000] or "(no CV on file yet)",
        jd=body.jd_text[:6000],
        role=body.role or "",
        company=body.company or "",
    )
    try:
        raw = _model().generate_content(prompt).text
        data = _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {e}")

    record = {
        "id": str(uuid.uuid4()),
        "user_id": str(user.id),
        "created_at": datetime.utcnow().isoformat(),
        "url": body.url,
        "company": body.company,
        "role": body.role,
        "evaluation": data,
    }
    _EVALUATIONS.setdefault(str(user.id), []).insert(0, record)

    # Auto-accumulate STAR stories into bank
    try:
        stories = data["blocks"]["F_interview_prep"]["stories"]
        bank = _STORY_BANK.setdefault(str(user.id), [])
        existing = {s["title"].lower() for s in bank}
        for s in stories:
            if s.get("title") and s["title"].lower() not in existing:
                bank.append({"id": str(uuid.uuid4()), **s, "source": body.company or "eval"})
    except Exception:
        pass

    return record


@router.get("/evaluations")
async def list_evaluations(user: User = Depends(get_current_user)):
    return _EVALUATIONS.get(str(user.id), [])[:50]


# ── CV Tailoring ─────────────────────────────────────────────────────────────

TAILOR_PROMPT = """You are an ATS-optimisation expert. Produce a tailored CV section plan.

CANDIDATE_CV:
{cv}

JOB_DESCRIPTION:
{jd}

Return ONLY JSON:
{{
  "tailored_summary": "2-3 sentence rewrite",
  "keywords_to_inject": ["kw", ...],
  "bullet_rewrites": [{{"original_hint": "", "rewrite": ""}}],
  "sections_to_reorder": ["Projects first because ..."],
  "ats_tips": [""]
}}
"""


@router.post("/tailor-cv")
async def tailor_cv(
    body: TailorCVBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cv = await _cv_summary(db, user)
    prompt = TAILOR_PROMPT.format(cv=cv[:5000] or "(no CV)", jd=body.jd_text[:6000])
    try:
        raw = _model().generate_content(prompt).text
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Tailor failed: {e}")


# ── Story Bank ───────────────────────────────────────────────────────────────

@router.get("/story-bank")
async def list_stories(user: User = Depends(get_current_user)):
    return _STORY_BANK.get(str(user.id), [])


@router.post("/story-bank")
async def add_story(body: StoryIn, user: User = Depends(get_current_user)):
    bank = _STORY_BANK.setdefault(str(user.id), [])
    story = {"id": str(uuid.uuid4()), **body.model_dump()}
    bank.append(story)
    return story


@router.delete("/story-bank/{sid}", status_code=204)
async def delete_story(sid: str, user: User = Depends(get_current_user)):
    bank = _STORY_BANK.get(str(user.id), [])
    _STORY_BANK[str(user.id)] = [s for s in bank if s["id"] != sid]


# ── Negotiation ──────────────────────────────────────────────────────────────

NEGO_PROMPT = """Draft salary-negotiation scripts for the candidate. Concrete lines,
not generic advice. 3 scripts: (1) counter current offer, (2) push back on a
geographic discount, (3) leverage a competing offer.

COMPANY: {company}
ROLE: {role}
CURRENT_OFFER: {current_offer}
TARGET: {target}
COMPETING: {competing}
GEO_CONTEXT: {geo}

Return ONLY JSON:
{{
  "scripts": [
    {{"title": "Counter", "script": "...", "why": "..."}},
    {{"title": "Geo pushback", "script": "...", "why": "..."}},
    {{"title": "Competing offer leverage", "script": "...", "why": "..."}}
  ],
  "walk_away_line": "",
  "anchors": ["concrete number anchors with source"]
}}
"""


@router.post("/negotiation")
async def negotiate(body: NegotiationBody, user: User = Depends(get_current_user)):
    prompt = NEGO_PROMPT.format(
        company=body.company, role=body.role,
        current_offer=body.current_offer or "unknown",
        target=body.target or "unknown",
        competing=body.competing_offers or "none",
        geo=body.geo_context or "n/a",
    )
    try:
        raw = _model().generate_content(prompt).text
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Negotiation failed: {e}")


# ── Portal Scan (LLM-summarised v1; real API-hit scanner is a follow-up) ─────

SCAN_PROMPT = """Suggest a prioritised list of 10 companies + 3 concrete portal
URLs each (Ashby/Greenhouse/Lever/careers page) to scan for roles matching:
QUERY: {query}
INCLUDE_COMPANIES: {companies}

Return ONLY JSON:
{{
  "suggestions": [
    {{"company": "", "why": "", "portals": ["https://..."], "example_query": ""}}
  ]
}}
Only include real, well-known companies. No invented URLs — if unsure, leave portals [].
"""


@router.post("/scan")
async def scan(body: ScanBody, user: User = Depends(get_current_user)):
    prompt = SCAN_PROMPT.format(query=body.query, companies=", ".join(body.companies) or "any")
    try:
        raw = _model().generate_content(prompt).text
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Scan failed: {e}")


@router.get("/health")
async def health():
    return {"ok": True, "ai": bool(_GEMINI_KEY)}
