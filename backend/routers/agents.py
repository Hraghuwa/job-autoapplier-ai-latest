from typing import Optional, List
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.dependencies import get_current_user, require_plan
from backend.models.user import User
from backend.models.agent_run import AgentRun, RunStatus
from backend.models.profile import UserProfile
from backend.schemas.agent import RunRequest, RunResponse, RunStatusResponse, ScheduleRequest
from backend.config import settings

router = APIRouter()

PHASE_PLATFORM = {
    1: "linkedin",
    2: "internshala",
    3: "wellfound",
    4: "naukri",
    5: "unstop",
    6: "web_search",
    7: "form_fill"
}



def _redis_available() -> bool:
    """Quick non-blocking check if Redis is reachable."""
    import socket
    try:
        from backend.config import settings as _s
        url = _s.redis_url  # redis://localhost:6379/0
        host = url.split("//")[1].split(":")[0]
        port = int(url.split(":")[-1].split("/")[0])
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _allowed_phases(user: User, requested: List[int]) -> List[int]:
    """Filter phases based on plan."""
    if user.plan == "free":
        return [p for p in requested if p == 1]  # free = LinkedIn only
    return requested


@router.post("/run", response_model=RunResponse)
async def run_agents(
    body: RunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.workers.agent_tasks import run_phase_task

    # Pre-run validation: ensure minimum setup is complete
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = profile_result.scalars().first()

    if not profile or not profile.resume_url:
        raise HTTPException(400, detail="Upload your resume before starting an agent run.")

    creds = profile.platform_passwords or {}
    needs_creds = {
        1: "linkedin", 
        2: "internshala", 
        3: "wellfound", 
        4: "naukri", 
        5: "unstop"
    }

    for phase in body.phases:
        platform = needs_creds.get(phase)
        if platform and not creds.get(platform, {}).get("email"):
            raise HTTPException(
                400,
                detail=f"Set your {platform.capitalize()} credentials before running Phase {phase}."
            )

    phases = _allowed_phases(user, body.phases)
    if not phases:
        raise HTTPException(400, "No phases available on your plan. Upgrade to Pro.")

    run_ids = []
    redis_up = _redis_available()

    for phase in phases:
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user.id,
            phase=phase,
            platform=PHASE_PLATFORM.get(phase),
            status=RunStatus.queued,
        )
        db.add(run)
        await db.flush()
        run_ids.append(str(run.id))

        # Queue to Celery if Redis is up
        if redis_up:
            try:
                run_phase_task.apply_async(
                    args=[str(user.id), phase, str(run.id)],
                    queue="agents",
                )
            except Exception:
                pass  # Celery queue failed; will fall through to thread below

    await db.commit()

    # Without Redis: run all phases SEQUENTIALLY in a single background thread.
    # Running them simultaneously would cause a CONFIG race condition — all phases
    # share the global CONFIG dict and would corrupt each other's credentials.
    if not redis_up:
        import threading
        from backend.workers.agent_tasks import _run_phase_logic

        def _run_phases_sequentially(uid: str, phase_run_pairs: list):
            for _phase, _run_id in phase_run_pairs:
                _run_phase_logic(uid, _phase, _run_id)

        phase_run_pairs = list(zip(phases, run_ids))
        t = threading.Thread(
            target=_run_phases_sequentially,
            args=(str(user.id), phase_run_pairs),
            daemon=True,
        )
        t.start()

    return RunResponse(run_ids=run_ids, message=f"Queued phases: {phases}")


@router.get("/status/{run_id}", response_model=RunStatusResponse)
async def run_status(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == uuid.UUID(run_id),
            AgentRun.user_id == user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    return RunStatusResponse.model_validate(run)


@router.get("/runs", response_model=List[RunStatusResponse])
async def list_runs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.user_id == user.id)
        .order_by(desc(AgentRun.started_at))
        .limit(20)
    )
    return [RunStatusResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/pause/{run_id}")
async def pause_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == uuid.UUID(run_id),
            AgentRun.user_id == user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    # Signal the in-process threading.Event (works for background threads)
    try:
        from backend.workers.agent_tasks import request_stop
        request_stop(run_id)
    except Exception:
        pass

    # Also set Redis key (works for Celery workers)
    try:
        import redis as _redis_sync
        r = _redis_sync.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
        r.set(f"pause:{run_id}", "1", ex=3600)
    except Exception:
        pass

    run.status = RunStatus.paused
    await db.commit()
    return {"message": "Stop signal sent"}


@router.post("/schedule")
async def schedule_run(
    body: ScheduleRequest,
    user: User = Depends(require_plan("pro")),
    db: AsyncSession = Depends(get_db),
):
    """Save cron schedule (picked up by Celery Beat). Pro only."""
    from sqlalchemy import select as sa_select
    from backend.models.profile import UserProfile
    result = await db.execute(sa_select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile:
        prefs = dict(profile.job_preferences or {})
        prefs["schedule"] = {"cron": body.cron, "phases": body.phases, "enabled": body.enabled}
        profile.job_preferences = prefs
        await db.commit()
    return {"message": "Schedule saved", "cron": body.cron}

@router.get("/schedule")
async def get_schedule(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select as sa_select
    from backend.models.profile import UserProfile
    result = await db.execute(sa_select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    
    schedule = {"cron": "0 9 * * *", "phases": [], "enabled": False}
    if profile and profile.job_preferences:
        schedule = profile.job_preferences.get("schedule", schedule)
        
    return schedule

@router.get("/runs/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.models.agent_run import AgentLog
    result = await db.execute(
        select(AgentLog).where(
            AgentLog.run_id == uuid.UUID(run_id)
        ).order_by(AgentLog.created_at)
    )
    # Return as dicts directly since LogResponse can handle from_attributes
    logs = result.scalars().all()
    from backend.schemas.agent import LogResponse
    return [LogResponse.model_validate(log) for log in logs]

@router.post("/runs/{run_id}/analyze")
async def analyze_run_logs(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.models.agent_run import AgentLog
    from backend.models.profile import UserProfile
    
    result = await db.execute(
        select(AgentLog).where(
            AgentLog.run_id == uuid.UUID(run_id),
            AgentLog.event_type == "error"
        ).order_by(AgentLog.created_at)
    )
    error_logs = result.scalars().all()
    if not error_logs:
        return {"message": "No errors to analyze in this run.", "advice": None}
        
    errors_text = "\n".join([f"- {log.message}" for log in error_logs])
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.system_gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
You are an expert AI agent coach. An automated job application agent failed with the following errors. 
Provide a concise, 1-2 sentence advice rule that the agent should follow to avoid these errors in the future. 
Do not include conversational flavor, just the directive.
ERRORS:
{errors_text}
"""
        response = model.generate_content(prompt)
        advice = response.text.strip()
        
        # Save to profile
        prof_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = prof_result.scalar_one_or_none()
        if profile:
            prefs = dict(profile.job_preferences or {})
            existing = prefs.get("agent_custom_instructions", "")
            if advice not in existing:
                prefs["agent_custom_instructions"] = f"{existing}\n{advice}".strip()
            profile.job_preferences = prefs
            await db.commit()
            
        return {"message": "Analyzed successfully", "advice": advice}
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")
