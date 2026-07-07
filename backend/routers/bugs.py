"""
Bug Report router + Self-Learn loop.

Endpoints:
  POST /bugs/report   — authenticated user submits a bug from any page.
                        Stores the report in profile.job_preferences["bug_reports"]
                        and IMMEDIATELY runs a Gemini analysis that converts the
                        report into a concrete agent rule. That rule is appended
                        to profile.job_preferences["agent_custom_instructions"],
                        which feeds directly into the LLM prompts used by every
                        agent phase (same pipeline as /agents/runs/{id}/analyze).

  GET  /bugs/list     — returns the calling user's bug reports (newest first).

The self-learn loop is intentionally best-effort: if Gemini is down or missing
an API key, the bug is still persisted and the endpoint returns 200 with
`advice = None` so the frontend dialog can close gracefully.
"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.config import settings
from backend.workers.agent_tasks import _ensure_dict


router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class BugReportRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=4000)
    page: Optional[str] = None          # frontend route the user was on
    severity: Optional[str] = "medium"  # low | medium | high
    console_snippet: Optional[str] = None
    user_agent: Optional[str] = None


class BugReportResponse(BaseModel):
    id: str
    created_at: str
    title: str
    description: str
    page: Optional[str]
    severity: Optional[str]
    status: str               # open | analyzed | resolved
    advice: Optional[str]     # Gemini-generated rule saved back to agent


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_profile(user: User, db: AsyncSession) -> UserProfile:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


def _analyze_bug_with_gemini(bug: dict) -> Optional[str]:
    """
    Turn a user's bug description into a concrete, actionable rule the agent
    LLMs should follow to prevent the same class of bug in future runs.
    Returns the advice string or None if analysis is unavailable.
    """
    if not getattr(settings, "system_gemini_key", None):
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.system_gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""You are an AI agent coach for a job auto-applier app.

A user filed this bug report:
TITLE: {bug.get('title')}
PAGE: {bug.get('page') or 'unknown'}
SEVERITY: {bug.get('severity') or 'medium'}
DESCRIPTION:
{bug.get('description')}

CONSOLE / ERROR SNIPPET (may be empty):
{bug.get('console_snippet') or '(none)'}

Produce 1–3 **actionable rules** the agent's form-filling / navigation LLM
should follow in future runs to prevent the same bug. Each rule should be
a single imperative sentence. Examples:

  - "If a Google login wall appears during web search, wait up to 2 minutes
     for the user to log in manually before skipping the query."
  - "Never close the search tab after applying to a job — always switch back
     to the first tab before the next driver.get()."
  - "When a dropdown has no exact match, pick the closest option instead of
     leaving it blank."

Avoid vague rules like "be more careful" or "handle errors better".
Output ONLY the rules, one per line, no numbering or extra commentary."""
        response = model.generate_content(prompt)
        return (response.text or "").strip() or None
    except Exception:
        return None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/report", response_model=BugReportResponse)
async def report_bug(
    body: BugReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    prefs = _ensure_dict(profile.job_preferences)

    # Build the bug record
    import uuid as _uuid
    bug_id = str(_uuid.uuid4())
    bug_record = {
        "id": bug_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": body.title.strip(),
        "description": body.description.strip(),
        "page": body.page,
        "severity": body.severity or "medium",
        "console_snippet": body.console_snippet,
        "user_agent": body.user_agent,
        "status": "open",
        "advice": None,
    }

    # Run the self-learn analysis before returning so the agent gets smarter
    # the instant the user reports something. Falls back silently if Gemini
    # is unavailable.
    advice = _analyze_bug_with_gemini(bug_record)
    if advice:
        bug_record["advice"] = advice
        bug_record["status"] = "analyzed"
        # Append the rule to agent_custom_instructions so EVERY subsequent
        # agent run sees it in its LLM prompts. This is the same field used
        # by /agents/runs/{id}/analyze so the self-learn pipeline stays unified.
        existing = (prefs.get("agent_custom_instructions") or "").strip()
        if advice not in existing:
            prefs["agent_custom_instructions"] = (
                f"{existing}\n{advice}".strip() if existing else advice
            )

    # Persist the bug report
    bug_log: List[dict] = list(prefs.get("bug_reports") or [])
    bug_log.append(bug_record)
    # Cap to the most recent 100 so we don't bloat job_preferences JSON forever.
    if len(bug_log) > 100:
        bug_log = bug_log[-100:]
    prefs["bug_reports"] = bug_log

    profile.job_preferences = prefs
    flag_modified(profile, "job_preferences")
    await db.commit()

    return BugReportResponse(**bug_record)


@router.get("/list", response_model=List[BugReportResponse])
async def list_bugs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    prefs = _ensure_dict(profile.job_preferences)
    bugs: List[dict] = list(prefs.get("bug_reports") or [])
    # newest-first
    bugs.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return [BugReportResponse(**b) for b in bugs]
