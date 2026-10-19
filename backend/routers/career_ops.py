"""Career-Ops — full port of the career-ops-main CLI.

Modes ported from /Users/hragh/Downloads/career-ops-main/modes/:
  - oferta.md           → POST /career-ops/evaluate         (A–G offer evaluation)
  - ofertas.md          → POST /career-ops/compare          (multi-offer 10-dim matrix)
  - tailor              → POST /career-ops/tailor-cv        (CV rewrites per JD)
  - scan.md             → POST /career-ops/scan             (portal target suggestions)
  - interview-prep.md   → POST /career-ops/story-bank       (STAR story CRUD)
  - negotiation         → POST /career-ops/negotiation      (counter / geo / leverage scripts)
  - project.md          → POST /career-ops/project-eval     (portfolio project 6-dim)
  - training.md         → POST /career-ops/training-eval    (course/cert 6-dim)
  - deep.md             → POST /career-ops/deep-research    (Perplexity-ready prompt)
  - patterns.md         → POST /career-ops/patterns         (rejection pattern detector)
  - followup.md         → POST /career-ops/followup         (cadence + draft generator)
  - contacto.md         → POST /career-ops/contact-strategy (LinkedIn outreach)

Robust against Gemini deprecations: every call walks a model fallback list
(`gemini-2.0-flash` → `gemini-flash-latest` → `gemini-2.5-flash` → `gemini-1.5-flash`
→ `gemini-1.5-flash-8b` → `gemini-1.5-pro`) before failing, and falls back to
Groq if the user has a Groq key configured.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.application import Application, ApplicationStatus
from backend.models.profile import UserProfile
from backend.services import followthrough
from backend.services.plan_gate import consume_ai_token
from backend.services.tracking_service import tracking_service

router = APIRouter()


# ── AI key resolution + multi-model fallback ────────────────────────────────

def _resolve_keys(user: Optional[User]) -> tuple[Optional[str], Optional[str]]:
    """Return (gemini_key, groq_key) from user → settings → env."""
    gemini = None
    groq = None
    if user is not None:
        try:
            from backend.services.crypto_service import decrypt
            if getattr(user, "gemini_key_encrypted", None):
                gemini = decrypt(user.gemini_key_encrypted)
            if getattr(user, "groq_key_encrypted", None):
                groq = decrypt(user.groq_key_encrypted)
        except Exception:
            pass
    gemini = (
        gemini or settings.system_gemini_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("SYSTEM_GEMINI_KEY")
    )
    groq = groq or os.environ.get("GROQ_API_KEY")
    return gemini, groq


# Model fallback list: newest first. `gemini-1.5-flash` was deprecated on
# v1beta in 2025 for some keys/regions — we no longer rely on it being available.
_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _gemini_call(api_key: str, prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    last_err: Optional[Exception] = None
    for name in _GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(name)
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", "") or "").strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Gemini models failed (last: {last_err})")


def _groq_call(api_key: str, prompt: str) -> str:
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("Groq SDK not installed (pip install groq)")
    client = Groq(api_key=api_key)
    last_err: Optional[Exception] = None
    for name in _GROQ_MODELS:
        try:
            resp = client.chat.completions.create(
                model=name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.7,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Groq models failed (last: {last_err})")


def _ai(prompt: str, user: Optional[User]) -> str:
    """Run prompt through the unified llm_router (Ollama → Gemini → Groq).

    Resume-tailoring / evaluate-offer / negotiation prompts are writer-role —
    longer prose, careful rewrites — so the router preferred order is
    local-Qwen-14B → Gemini Flash → Groq Llama-70B.

    Falls back to the in-file Gemini/Groq direct calls only if `llm_router`
    is unimportable (defensive — should not happen in normal deploys).
    """
    consume_ai_token(user)
    import sys, os as _os
    _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    gemini, groq = _resolve_keys(user)
    errs: list[str] = []

    try:
        from llm_router import generate
        cfg = {}
        if gemini: cfg["gemini_api_key"] = gemini
        if groq:   cfg["groq_api_key"]   = groq
        out = generate(prompt, role="writer", config=cfg, max_tokens=2048)
        if out:
            return out
        errs.append("llm_router: no provider returned a response")
    except ImportError:
        # Defensive — keep working if llm_router was removed.
        if gemini:
            try:
                return _gemini_call(gemini, prompt)
            except Exception as e:
                errs.append(f"gemini: {type(e).__name__}: {str(e)[:160]}")
        if groq:
            try:
                return _groq_call(groq, prompt)
            except Exception as e:
                errs.append(f"groq: {type(e).__name__}: {str(e)[:160]}")

    if not gemini and not groq:
        raise HTTPException(503, "AI engine not configured. Add a Gemini or Groq API key in Settings → API Keys (or start Ollama locally).")
    raise HTTPException(502, f"All AI providers failed. {' | '.join(errs)}")


def _parse_json(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip("` \n")
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        t = m.group(0)
    return json.loads(t)


# In-memory caches (per-user). Survives process lifetime only — DB migration in v2.
_STORY_BANK: Dict[str, List[Dict[str, Any]]] = {}
_EVALUATIONS: Dict[str, List[Dict[str, Any]]] = {}


async def _cv_summary(db: AsyncSession, user: User) -> str:
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
    jd_text: str = Field(..., min_length=40)
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
    query: str
    companies: List[str] = Field(default_factory=list)


class CompareBody(BaseModel):
    offers: List[Dict[str, Any]] = Field(..., description="List of {company, role, jd_text, comp?, remote?}")


class ProjectEvalBody(BaseModel):
    project_idea: str
    target_role: Optional[str] = ""


class TrainingEvalBody(BaseModel):
    course_or_cert: str
    target_role: Optional[str] = ""
    weeks_available: Optional[int] = None


class DeepResearchBody(BaseModel):
    company: str
    role: str
    jd_text: Optional[str] = ""


class PatternsBody(BaseModel):
    applications: List[Dict[str, Any]] = Field(
        ..., description="List of {company, role, archetype?, score?, status, blockers?, remote_policy?}"
    )


class FollowupBody(BaseModel):
    company: str
    role: str
    status: str = Field(..., description="applied | responded | interview")
    days_since_action: int
    last_message: Optional[str] = ""
    application_id: Optional[str] = None  # saves the draft on that application


class ContactBody(BaseModel):
    company: str
    role: str
    contact_type: str = Field("recruiter", description="recruiter | hiring_manager | peer | interviewer")
    contact_name: Optional[str] = ""
    contact_signal: Optional[str] = ""
    language: str = "en"


# ── Block A–G Evaluation (oferta.md) ─────────────────────────────────────────

EVAL_PROMPT = """You are career-ops, an A–F offer evaluator with a G (legitimacy) block.
Return ONLY valid JSON. Be specific, no placeholders. Scores 0-5 (one decimal ok).

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
"""


@router.post("/evaluate")
async def evaluate_offer(
    body: EvaluateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cv = await _cv_summary(db, user)
    prompt = EVAL_PROMPT.format(
        cv=cv[:5000] or "(no CV on file yet)",
        jd=body.jd_text[:6000],
        role=body.role or "",
        company=body.company or "",
    )
    raw = _ai(prompt, user)
    try:
        data = _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Could not parse evaluation JSON: {e}")

    record = {
        "id": str(uuid.uuid4()),
        "user_id": str(user.id),
        "created_at": datetime.utcnow().isoformat(),
        "url": body.url, "company": body.company, "role": body.role,
        "evaluation": data,
    }
    _EVALUATIONS.setdefault(str(user.id), []).insert(0, record)

    # Auto-accumulate STAR stories
    try:
        for s in data["blocks"]["F_interview_prep"]["stories"]:
            bank = _STORY_BANK.setdefault(str(user.id), [])
            existing = {st["title"].lower() for st in bank}
            if s.get("title") and s["title"].lower() not in existing:
                bank.append({"id": str(uuid.uuid4()), **s, "source": body.company or "eval"})
    except Exception:
        pass
    return record


@router.get("/evaluations")
async def list_evaluations(user: User = Depends(get_current_user)):
    return _EVALUATIONS.get(str(user.id), [])


# ── Multi-Offer Comparison (ofertas.md) ──────────────────────────────────────

COMPARE_PROMPT = """Multi-offer comparison using a 10-dimension weighted scoring matrix.
Weights (sum=100): north_star_alignment 25, cv_match 15, level 15, comp 10,
growth_trajectory 10, remote_quality 5, company_reputation 5, tech_modernity 5,
speed_to_offer 5, cultural_signals 5.

Score each dimension 1-5 per offer, compute weighted total, rank.

CANDIDATE_CV:
{cv}

OFFERS:
{offers}

Return ONLY JSON:
{{
  "ranking": [
    {{
      "rank": 1, "company": "", "role": "",
      "weighted_total": 0.0,
      "scores": {{"north_star_alignment":0,"cv_match":0,"level":0,"comp":0,"growth_trajectory":0,"remote_quality":0,"company_reputation":0,"tech_modernity":0,"speed_to_offer":0,"cultural_signals":0}},
      "verdict": "PURSUE|HOLD|DROP",
      "rationale": ""
    }}
  ],
  "recommendation": "one paragraph on time-to-offer and what to prioritise"
}}
"""


@router.post("/compare")
async def compare_offers(
    body: CompareBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(body.offers) < 2:
        raise HTTPException(400, "Need at least 2 offers to compare")
    cv = await _cv_summary(db, user)
    raw = _ai(
        COMPARE_PROMPT.format(cv=cv[:3500] or "(no CV)", offers=json.dumps(body.offers)[:6000]),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Compare parse failed: {e}")


# ── Tailor CV ────────────────────────────────────────────────────────────────

TAILOR_PROMPT = """Tailor the candidate's CV to the JD. Surgical edits only —
do not invent experience. Return JSON.
{data_rule}

CV:
{cv}

EXPERIENCE ENTRIES (index: role at company — current description):
{experiences}

{jd}

Return ONLY JSON:
{{
  "tailored_summary": "2-3 sentences",
  "keywords_to_inject": ["kw1","kw2"],
  "bullet_rewrites": [{{"experience_index": 0, "rewrite": "the whole description of that entry, rewritten in stronger XYZ-formula bullets, using only facts already in it"}}],
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
    from backend.services.untrusted import DATA_RULE, fence
    cv = await _cv_summary(db, user)
    exps = _experiences(await _profile(db, user))
    raw = _ai(TAILOR_PROMPT.format(
        cv=cv[:5000] or "(no CV)", data_rule=DATA_RULE.format(tag="job_posting"),
        experiences="\n".join(f"{i}: {e.get('role', '')} at {e.get('company', '')} — "
                              f"{str(e.get('description') or '')[:600]}" for i, e in enumerate(exps)) or "(none)",
        jd=fence(body.jd_text[:6000])), user)
    try:
        out = _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Tailor failed: {e}")
    # Attach what each rewrite would replace so the user can compare before applying.
    rewrites = []
    for r in out.get("bullet_rewrites") or []:
        i = r.get("experience_index") if isinstance(r, dict) else None
        if isinstance(i, int) and 0 <= i < len(exps) and str(r.get("rewrite") or "").strip():
            rewrites.append({"experience_index": i, "rewrite": r["rewrite"].strip(),
                             "role": exps[i].get("role", ""), "company": exps[i].get("company", ""),
                             "original": exps[i].get("description", "")})
    out["bullet_rewrites"] = rewrites
    return out


def _experiences(profile: UserProfile) -> List[Dict[str, Any]]:
    exps = (profile.extracted_data or {}).get("experience") or []
    return [e for e in exps if isinstance(e, dict)] if isinstance(exps, list) else []


class Rewrite(BaseModel):
    experience_index: int = Field(..., ge=0)
    rewrite: str = Field(..., min_length=1, max_length=3000)


class ApplyTailorBody(BaseModel):
    summary: Optional[str] = Field(None, max_length=1500)
    skills_add: List[str] = Field(default_factory=list, max_length=30)
    rewrites: List[Rewrite] = Field(default_factory=list, max_length=30)


@router.post("/tailor-cv/apply")
async def apply_tailor(body: ApplyTailorBody, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Save the rewrites the user accepted into their profile, so every AI
    Mission's resume (and its per-job tailoring) starts from them. The previous
    values are kept for one-step undo via POST /tailor-cv/undo."""
    import copy
    from sqlalchemy.orm.attributes import flag_modified
    profile = await _profile(db, user)
    data = copy.deepcopy(profile.extracted_data or {})
    autofill = dict(profile.autofill_bank or {})
    data["_before_tailor_apply"] = copy.deepcopy({  # deep: rewrites below mutate experience in place
        "summary": data.get("summary"), "skills": data.get("skills"),
        "experience": data.get("experience"), "autofill_skills": autofill.get("skills"),
    })
    if body.summary and body.summary.strip():
        data["summary"] = body.summary.strip()
    if body.skills_add:
        skills = data.get("skills") or []
        skills = [s.strip() for s in skills.split(",")] if isinstance(skills, str) else list(skills)
        have = {str(s).lower() for s in skills}
        new = [s.strip() for s in body.skills_add if s.strip() and s.strip().lower() not in have]
        data["skills"] = skills + new
        # Missions read autofill_bank.skills first when the user has set it.
        if new and autofill.get("skills"):
            autofill["skills"] = ", ".join([autofill["skills"]] + new)
            profile.autofill_bank = autofill
            flag_modified(profile, "autofill_bank")
    exps = data.get("experience") if isinstance(data.get("experience"), list) else []
    for r in body.rewrites:
        if r.experience_index >= len(exps) or not isinstance(exps[r.experience_index], dict):
            raise HTTPException(400, f"No experience entry {r.experience_index}")
        exps[r.experience_index]["description"] = r.rewrite.strip()
    profile.extracted_data = data
    flag_modified(profile, "extracted_data")
    await db.commit()
    return {"summary": data.get("summary"), "skills": data.get("skills"),
            "experience": data.get("experience"), "undo_available": True}


@router.post("/tailor-cv/undo")
async def undo_tailor(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm.attributes import flag_modified
    profile = await _profile(db, user)
    data = dict(profile.extracted_data or {})
    before = data.pop("_before_tailor_apply", None)
    if not before:
        raise HTTPException(404, "Nothing to undo.")
    for k in ("summary", "skills", "experience"):
        data[k] = before.get(k)
    autofill = dict(profile.autofill_bank or {})
    if before.get("autofill_skills") is not None:
        autofill["skills"] = before["autofill_skills"]
        profile.autofill_bank = autofill
        flag_modified(profile, "autofill_bank")
    profile.extracted_data = data
    flag_modified(profile, "extracted_data")
    await db.commit()
    return {"restored": True}


# ── Story Bank (STAR + Reflection) ───────────────────────────────────────────

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

NEGO_PROMPT = """Draft salary-negotiation scripts. Concrete lines, not generic advice.
3 scripts: (1) counter current offer, (2) push back on geographic discount,
(3) leverage a competing offer.

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
    raw = _ai(
        NEGO_PROMPT.format(
            company=body.company, role=body.role,
            current_offer=body.current_offer or "unknown",
            target=body.target or "unknown",
            competing=body.competing_offers or "none",
            geo=body.geo_context or "n/a",
        ),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Negotiation parse failed: {e}")


# ── Portal Scan ──────────────────────────────────────────────────────────────

SCAN_PROMPT = """Suggest a prioritised list of 10 companies + 3 concrete portal
URLs each (Ashby/Greenhouse/Lever/careers page) for roles matching:
QUERY: {query}
INCLUDE_COMPANIES: {companies}

Return ONLY JSON:
{{"suggestions": [{{"company":"","why":"","portals":["https://..."],"example_query":""}}]}}
Only real, well-known companies. No invented URLs — if unsure, leave portals [].
If the company hires through Greenhouse or Lever, include that board URL
(https://boards.greenhouse.io/<slug> or https://jobs.lever.co/<slug>) — AI
Missions pull every open role from those boards automatically.
"""


@router.post("/scan")
async def scan(body: ScanBody, user: User = Depends(get_current_user)):
    raw = _ai(SCAN_PROMPT.format(query=body.query, companies=", ".join(body.companies) or "any"), user)
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Scan parse failed: {e}")


# ── Portal Scan → AI Mission targets ─────────────────────────────────────────
# Saved targets live in job_preferences: names in "target_companies" (the web
# mission's Google site: queries) and verified Greenhouse/Lever boards in
# "target_boards" (the web mission pulls every posting from them via API).

_BOARD_URL = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)")),
]
_BOARD_API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
}


def parse_board(url: str) -> Optional[tuple]:
    for kind, rx in _BOARD_URL:
        m = rx.search(url or "")
        if m and m.group(1).lower() not in {"embed", "jobs"}:
            return kind, m.group(1).lower()
    return None


async def _open_jobs(kind: str, slug: str) -> Optional[int]:
    """Open-role count from the board's public API, or None if the board doesn't
    exist — the scan LLM sometimes invents portal URLs."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(_BOARD_API[kind].format(slug))
        if r.status_code != 200:
            return None
        data = r.json()
        jobs = data.get("jobs") if kind == "greenhouse" else data
        return len(jobs) if isinstance(jobs, list) else None
    except Exception:
        return None


async def _profile(db: AsyncSession, user: User) -> UserProfile:
    p = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
    if not p:
        raise HTTPException(400, "Finish onboarding (upload a resume) first.")
    return p


class TargetIn(BaseModel):
    company: str = Field(..., min_length=1, max_length=120)
    portals: List[str] = Field(default_factory=list, max_length=10)


class SaveTargetsBody(BaseModel):
    targets: List[TargetIn] = Field(..., min_length=1, max_length=30)


@router.get("/mission-targets")
async def mission_targets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prefs = (await _profile(db, user)).job_preferences or {}
    return {"companies": prefs.get("target_companies") or [], "boards": prefs.get("target_boards") or []}


@router.post("/mission-targets")
async def save_mission_targets(body: SaveTargetsBody, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Save Portal Scan picks as AI Mission targets (merged, de-duplicated)."""
    import asyncio
    from sqlalchemy.orm.attributes import flag_modified
    profile = await _profile(db, user)
    prefs = dict(profile.job_preferences or {})
    companies = list(prefs.get("target_companies") or [])
    boards = list(prefs.get("target_boards") or [])
    have = {c.lower() for c in companies}
    for t in body.targets:
        if t.company.strip().lower() not in have:
            companies.append(t.company.strip())
            have.add(t.company.strip().lower())
    candidates = {}
    for t in body.targets:
        for url in t.portals:
            b = parse_board(url)
            if b and b not in {(x["kind"], x["slug"]) for x in boards}:
                candidates.setdefault(b, t.company.strip())
    counts = await asyncio.gather(*(_open_jobs(k, s) for k, s in candidates))
    added, unverified = [], []
    for ((kind, slug), company), n in zip(candidates.items(), counts):
        if n is None:
            unverified.append(f"{kind}:{slug}")
        else:
            entry = {"kind": kind, "slug": slug, "company": company, "open_jobs": n}
            boards.append(entry)
            added.append(entry)
    prefs["target_companies"], prefs["target_boards"] = companies[:100], boards[:60]
    profile.job_preferences = prefs
    flag_modified(profile, "job_preferences")
    await db.commit()
    return {"companies": prefs["target_companies"], "boards": prefs["target_boards"],
            "boards_added": added, "unverified_portals": unverified}


@router.delete("/mission-targets/{company}")
async def delete_mission_target(company: str, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm.attributes import flag_modified
    profile = await _profile(db, user)
    prefs = dict(profile.job_preferences or {})
    key = company.strip().lower()
    prefs["target_companies"] = [c for c in prefs.get("target_companies") or [] if c.lower() != key]
    prefs["target_boards"] = [b for b in prefs.get("target_boards") or []
                              if (b.get("company") or "").lower() != key and b.get("slug") != key]
    profile.job_preferences = prefs
    flag_modified(profile, "job_preferences")
    await db.commit()
    return {"companies": prefs["target_companies"], "boards": prefs["target_boards"]}


# ── Portfolio Project Evaluation (project.md) ────────────────────────────────

PROJECT_PROMPT = """Evaluate a portfolio project on 6 dimensions (1-5 each):
- signal_for_role (weight 25%) — directly demonstrates JD skills
- uniqueness (20%) — nobody else has this
- demoability (20%) — live demo in 2 min
- metrics_potential (15%) — clear latency/cost/accuracy metrics
- time_to_mvp (10%) — under 1 week is 5
- star_potential (10%) — story-rich with trade-offs

PROJECT_IDEA: {idea}
TARGET_ROLE: {role}

Return ONLY JSON:
{{
  "scores": {{"signal_for_role":0,"uniqueness":0,"demoability":0,"metrics_potential":0,"time_to_mvp":0,"star_potential":0}},
  "weighted_total": 0.0,
  "verdict": "BUILD|SKIP|PIVOT",
  "pivot_to": "(if PIVOT) — alternative project idea",
  "interview_pack": {{"one_pager": "", "demo_plan": "", "postmortem_seeds": [""]}},
  "milestones": {{"week_1": "", "week_2": ""}},
  "rationale": ""
}}
"""


@router.post("/project-eval")
async def project_eval(body: ProjectEvalBody, user: User = Depends(get_current_user)):
    raw = _ai(
        PROJECT_PROMPT.format(idea=body.project_idea[:3000], role=body.target_role or "(unspecified)"),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Project eval parse failed: {e}")


# ── Training / Course Evaluation (training.md) ───────────────────────────────

TRAINING_PROMPT = """Evaluate a course/cert on 6 dimensions:
- north_star_alignment, recruiter_signal, time_effort, opportunity_cost,
  risks (outdated content, weak brand, too basic), portfolio_deliverable.

COURSE_OR_CERT: {item}
TARGET_ROLE: {role}
WEEKS_AVAILABLE: {weeks}

Verdicts: DO | DO_TIMEBOXED (specify max weeks) | DON'T (with better alternative).

Return ONLY JSON:
{{
  "evaluation": {{"north_star_alignment":"","recruiter_signal":"","time_effort":"","opportunity_cost":"","risks":"","portfolio_deliverable":""}},
  "verdict": "DO|DO_TIMEBOXED|DONT",
  "max_weeks": 0,
  "weekly_plan": [{{"week": 1, "deliverable": ""}}],
  "alternative_if_dont": "",
  "production_grade_ai_priority": "evals|observability|cost_reliability|governance|enterprise_arch|n/a"
}}
"""


@router.post("/training-eval")
async def training_eval(body: TrainingEvalBody, user: User = Depends(get_current_user)):
    raw = _ai(
        TRAINING_PROMPT.format(
            item=body.course_or_cert[:1500],
            role=body.target_role or "",
            weeks=body.weeks_available or "unspecified",
        ),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Training eval parse failed: {e}")


# ── Deep Research Prompt Generator (deep.md) ─────────────────────────────────

DEEP_PROMPT = """Generate a Perplexity-ready deep-research prompt structured in 6 axes:
1. AI strategy   2. Recent moves (6mo)   3. Engineering culture
4. Likely challenges   5. Competitors & differentiation   6. Candidate angle

COMPANY: {company}
ROLE: {role}
JD_CONTEXT: {jd}
CANDIDATE_CV: {cv}

Return ONLY JSON:
{{
  "research_prompt": "## Deep Research: {company} — {role}\\n\\n[full markdown prompt with all 6 sections personalised]",
  "key_questions": ["..."],
  "suggested_sources": ["company eng blog","glassdoor","blind","linkedin recent posts"]
}}
"""


@router.post("/deep-research")
async def deep_research(
    body: DeepResearchBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cv = await _cv_summary(db, user)
    raw = _ai(
        DEEP_PROMPT.format(company=body.company, role=body.role, jd=(body.jd_text or "")[:2500], cv=cv[:1500] or "(none)"),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Deep research parse failed: {e}")


# ── Rejection Pattern Detector (patterns.md) ─────────────────────────────────

PATTERNS_PROMPT = """Analyze application outcomes and surface actionable patterns.
Outcome buckets: positive (Interview/Offer/Responded/Applied), negative (Rejected/Discarded),
self_filtered (SKIP), pending (Evaluated only).

APPLICATIONS:
{apps}

Return ONLY JSON:
{{
  "metadata": {{"total": 0, "positive": 0, "negative": 0, "self_filtered": 0, "pending": 0}},
  "funnel": [{{"stage": "Evaluated", "count": 0, "pct": 0}}],
  "score_vs_outcome": [{{"outcome": "positive", "avg_score": 0, "min": 0, "max": 0, "count": 0}}],
  "archetype_performance": [{{"archetype": "", "total": 0, "positive": 0, "conversion_pct": 0}}],
  "top_blockers": [{{"blocker": "geo-restriction", "count": 0, "pct_of_apps": 0}}],
  "remote_policy_patterns": [{{"policy": "global", "total": 0, "positive": 0, "conversion_pct": 0}}],
  "tech_stack_gaps": [{{"skill": "", "count": 0}}],
  "recommended_score_threshold": {{"value": 0.0, "reasoning": ""}},
  "recommendations": [{{"impact": "HIGH|MED|LOW", "action": "", "reasoning": ""}}]
}}
"""


@router.post("/patterns")
async def patterns(body: PatternsBody, user: User = Depends(get_current_user)):
    if len(body.applications) < 5:
        raise HTTPException(
            400,
            f"Not enough data — need at least 5 applications, got {len(body.applications)}. "
            "Keep applying and come back when you have more outcomes to analyze.",
        )
    raw = _ai(PATTERNS_PROMPT.format(apps=json.dumps(body.applications)[:8000]), user)
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Patterns parse failed: {e}")


# ── Follow-up Cadence + Draft Generator (followup.md) ────────────────────────

FOLLOWUP_PROMPT = """Generate a follow-up draft (email or LinkedIn) appropriate
to the cadence stage. Cadence rules: applied = 7d, responded = 3d, interview = 1d.

COMPANY: {company}
ROLE: {role}
STATUS: {status}
DAYS_SINCE_LAST_ACTION: {days}
LAST_MESSAGE_FROM_THEM: {last}

Return ONLY JSON:
{{
  "urgency": "URGENT|OVERDUE|WAITING|COLD",
  "rationale": "",
  "email_draft": {{"subject": "", "body": ""}},
  "linkedin_draft": "",
  "next_followup_in_days": 0,
  "close_loop_advice": ""
}}
Tone: professional, concise, never desperate. No corporate-speak.
"""


@router.post("/followup")
async def followup(body: FollowupBody, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    app = await _own_app(db, user, body.application_id) if body.application_id else None
    if app is not None and sum(1 for h in (app.history or [])
                               if h.get("type") == followthrough.FOLLOWUP_EVENT) >= followthrough.MAX_FOLLOWUPS:
        raise HTTPException(409, f"Already {followthrough.MAX_FOLLOWUPS} follow-ups on this "
                                 "application — more reads as pestering. Move on or record the outcome.")
    raw = _ai(
        FOLLOWUP_PROMPT.format(
            company=body.company, role=body.role, status=body.status,
            days=body.days_since_action, last=(body.last_message or "(none)")[:1500],
        ),
        user,
    )
    try:
        out = _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Followup parse failed: {e}")
    if app is not None:
        # Persisted on the application (was an in-memory dict lost on restart);
        # followups_due() counts these to cap follow-ups at MAX_FOLLOWUPS.
        await tracking_service.log_event(db, app, followthrough.FOLLOWUP_EVENT,
                                         f"Follow-up drafted ({out.get('urgency', '')})", out)
        await db.commit()
    return out


# ── After applying: quiet applications, skill gaps, outcomes from Gmail ──────

async def _own_app(db: AsyncSession, user: User, app_id: str) -> Application:
    try:
        aid = uuid.UUID(str(app_id))
    except ValueError:
        raise HTTPException(400, "Bad application_id")
    app = (await db.execute(select(Application).where(
        Application.id == aid, Application.user_id == user.id))).scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Application not found")
    return app


async def _app_dicts(db: AsyncSession, user: User) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Application).where(Application.user_id == user.id))).scalars().all()
    return [{"id": a.id, "company": a.company, "job_title": a.job_title, "status": a.status,
             "applied_at": a.applied_at, "history": a.history, "missing_skills": a.missing_skills}
            for a in rows]


@router.get("/followups/due")
async def followups_due(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Applications gone quiet past their cadence — draft one via POST /followup
    with application_id. Drafts only; nothing is ever sent."""
    return followthrough.followups_due(await _app_dicts(db, user))


@router.get("/followups/{app_id}")
async def followup_drafts(app_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    app = await _own_app(db, user, app_id)
    return [{"created_at": h.get("timestamp"), **(h.get("data") or {})}
            for h in (app.history or []) if h.get("type") == followthrough.FOLLOWUP_EVENT]


@router.get("/skill-gaps")
async def skill_gaps(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return followthrough.skill_gaps(await _app_dicts(db, user))


UPSKILL_PROMPT = """Build a learning plan for a job seeker from the skill gaps
their own job applications revealed (weight = how often employers asked for it;
roles that reached interview count double).

CANDIDATE: {cv}
GAPS (skill, weight): {gaps}
HOURS PER WEEK AVAILABLE: {hours}

Prioritise by weight and by how quickly each gap can be closed. Prefer free,
well-known resources (official docs, freeCodeCamp, Coursera audit, YouTube
courses from established channels) and name them specifically. Skip any gap
the candidate already covers. Return ONLY JSON:
{{
  "plan": [{{"skill": "", "why": "", "resources": [""], "hours": 0, "proof_project": ""}}],
  "total_weeks": 0,
  "quick_wins": [""]
}}"""


class UpskillBody(BaseModel):
    hours_per_week: int = Field(6, ge=1, le=60)


@router.post("/skill-gaps/plan")
async def skill_gap_plan(body: UpskillBody, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    gaps = followthrough.skill_gaps(await _app_dicts(db, user))
    if not gaps:
        raise HTTPException(400, "No skill gaps recorded yet — apply to a few jobs first.")
    raw = _ai(UPSKILL_PROMPT.format(cv=(await _cv_summary(db, user))[:2500] or "(none)",
                                    gaps=json.dumps(gaps), hours=body.hours_per_week), user)
    try:
        return {"gaps": gaps, **_parse_json(raw)}
    except Exception as e:
        raise HTTPException(500, f"Plan parse failed: {e}")


class GmailScanBody(BaseModel):
    email: str
    app_password: str = Field(..., min_length=16, max_length=32,
                              description="Gmail app password; used for this scan only, never stored")
    days: int = Field(30, ge=1, le=120)


@router.post("/outcomes/gmail-scan")
async def gmail_scan(body: GmailScanBody, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Read recent Gmail (read-only IMAP) and PROPOSE status changes, citing the
    source email. Nothing is written — approve via POST /outcomes/apply."""
    import asyncio
    import imaplib
    try:
        mails = await asyncio.to_thread(followthrough.fetch_gmail, body.email,
                                        body.app_password.replace(" ", ""), body.days)
    except imaplib.IMAP4.error:
        raise HTTPException(401, "Gmail rejected the login — use an app password "
                                 "(Google Account → Security → App passwords) with IMAP enabled.")
    except OSError as e:
        raise HTTPException(502, f"Could not reach Gmail: {type(e).__name__}")
    return {"scanned": len(mails),
            "proposals": followthrough.propose_outcomes(mails, await _app_dicts(db, user))}


class OutcomeUpdate(BaseModel):
    application_id: str
    status: str
    evidence: Optional[str] = ""


class ApplyOutcomesBody(BaseModel):
    updates: List[OutcomeUpdate] = Field(..., max_length=200)


@router.post("/outcomes/apply")
async def apply_outcomes(body: ApplyOutcomesBody, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Apply the proposals the user approved."""
    done = []
    for u in body.updates:
        try:
            status = ApplicationStatus(u.status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {u.status}")
        app = await _own_app(db, user, u.application_id)
        await tracking_service.update_status(db, app, status, reason=f"From email: {u.evidence}"[:500])
        done.append(u.application_id)
    await db.commit()
    return {"updated": done}


# ── LinkedIn Outreach (contacto.md) ──────────────────────────────────────────

CONTACT_PROMPT = """Write a LinkedIn outreach using the 3-sentence framework.
Max 300 chars (LinkedIn connection-request limit). NO corporate-speak.
NO "I'm passionate about". Make them want to reply.

CONTACT_TYPE: {ctype}   — recruiter | hiring_manager | peer | interviewer
CONTACT_NAME: {cname}
CONTACT_SIGNAL: {csig}   (something specific about them — blog, talk, hire, project)
COMPANY: {company}
ROLE: {role}
CANDIDATE_CV: {cv}
LANGUAGE: {lang}

Tailor by type:
- recruiter:        sentence 1 = fit criteria; 2 = pre-empt screening; 3 = "Happy to share my CV…"
- hiring_manager:   1 = hook on team challenge; 2 = quantified accomplishment; 3 = "Would love to hear how your team approaches…"
- peer:             1 = genuine reference to their work; 2 = adjacent work I'm doing; 3 = "Would love your take on…"  (do NOT ask for a job)
- interviewer:      1 = research reference; 2 = light experience tie-in; 3 = "Looking forward to our chat on [date]"

Return ONLY JSON:
{{
  "primary_message": "≤300 chars",
  "alternates": ["alt1", "alt2"],
  "rationale": "why this opener works for this contact type",
  "alternate_targets": [{{"name": "", "title": "", "why_good_secondary": ""}}]
}}
"""


@router.post("/contact-strategy")
async def contact_strategy(
    body: ContactBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.contact_type not in {"recruiter", "hiring_manager", "peer", "interviewer"}:
        raise HTTPException(400, "contact_type must be recruiter | hiring_manager | peer | interviewer")
    cv = await _cv_summary(db, user)
    raw = _ai(
        CONTACT_PROMPT.format(
            ctype=body.contact_type, cname=body.contact_name or "(unknown)",
            csig=body.contact_signal or "(none)",
            company=body.company, role=body.role,
            cv=cv[:1500] or "(none)", lang=body.language,
        ),
        user,
    )
    try:
        return _parse_json(raw)
    except Exception as e:
        raise HTTPException(500, f"Contact parse failed: {e}")


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    g, q = _resolve_keys(None)
    return {"ok": True, "providers": {"gemini": bool(g), "groq": bool(q)},
            "models_tried": _GEMINI_MODELS}
