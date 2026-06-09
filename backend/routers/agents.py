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
from backend.workers.agent_tasks import _ensure_dict

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


def _celery_worker_listening(queue: str = "agents", timeout: float = 0.5) -> bool:
    """True iff at least one Celery worker is consuming `queue`.

    Used to decide whether queuing a task will actually get processed, or
    whether we should fall back to running it in-process. Without this check,
    a reachable Redis with no worker = tasks queued forever and the agent
    never opens a browser tab.
    """
    try:
        from backend.workers.celery_app import celery_app
        insp = celery_app.control.inspect(timeout=timeout)
        active = insp.active_queues() or {}
        for queues in active.values():
            for q in queues or []:
                if q.get("name") == queue:
                    return True
        return False
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

    # SQLite/SQLAlchemy can return `platform_passwords` as a raw JSON string,
    # list, or None depending on how the row was seeded. `_ensure_dict` guarantees
    # we get a dict so the `.get(platform, {}).get("email")` chain below does not
    # crash with `'str' object has no attribute 'get'`.
    creds = _ensure_dict(profile.platform_passwords)
    needs_creds = {
        1: "linkedin",
        2: "internshala",
        3: "wellfound",
        4: "naukri",
        5: "unstop"
    }

    for phase in body.phases:
        platform = needs_creds.get(phase)
        if platform:
            nested = creds.get(platform)
            if not isinstance(nested, dict) or not nested.get("email") or not nested.get("password"):
                raise HTTPException(
                    400,
                    detail=f"Set your {platform.capitalize()} credentials before running Phase {phase}."
                )

    phases = _allowed_phases(user, body.phases)
    if not phases:
        raise HTTPException(400, "No phases available on your plan. Upgrade to Pro.")

    run_ids = []
    # Use Celery ONLY if Redis is reachable AND a worker is actually
    # consuming the agents queue. Otherwise the task would sit in Redis
    # forever and the user would see "queued" with no browser tab and no
    # logs — the exact failure mode that bit us in production.
    redis_up = _redis_available()
    worker_up = _celery_worker_listening("agents") if redis_up else False
    use_celery = redis_up and worker_up

    fallback_pairs = []
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

        if use_celery:
            try:
                run_phase_task.apply_async(
                    args=[str(user.id), phase, str(run.id), bool(body.dry_run)],
                    queue="agents",
                )
            except Exception:
                fallback_pairs.append((phase, str(run.id)))
        else:
            fallback_pairs.append((phase, str(run.id)))

    await db.commit()

    # Fallback: run all phases SEQUENTIALLY in a single background thread.
    # Triggered when there is no Redis, no worker consuming `agents`, or
    # the enqueue raised. Sequential is required because all phases share
    # the global CONFIG dict and parallel runs would corrupt credentials.
    if fallback_pairs:
        import threading
        from backend.workers.agent_tasks import _run_phase_logic

        def _run_phases_sequentially(uid: str, phase_run_pairs: list, dry: bool):
            for _phase, _run_id in phase_run_pairs:
                _run_phase_logic(uid, _phase, _run_id, dry_run=dry)

        t = threading.Thread(
            target=_run_phases_sequentially,
            args=(str(user.id), fallback_pairs, bool(body.dry_run)),
            daemon=True,
        )
        t.start()

    return RunResponse(run_ids=run_ids, message=f"Queued phases: {phases}")


@router.get("/healthcheck")
async def agent_healthcheck():
    """Public dependency probe — Redis, Celery worker, Chrome binary, Ollama.

    The UI polls this so users see *why* a run can't start instead of staring
    at a queued spinner. `ok` is True iff the hard requirements (Chrome) pass —
    everything else is degraded but still works via fallbacks.
    """
    from backend.services.agent_supervisor import healthcheck, ensure_worker_running
    snap = healthcheck()
    # Self-heal opportunistically: every healthcheck poll re-spawns the worker
    # if it died. Cheap because ensure_worker_running short-circuits when alive.
    if snap["redis"] and not snap["celery_worker"]:
        ensure_worker_running()
        snap["celery_worker"] = healthcheck()["celery_worker"]
    return snap


@router.get("/preflight")
async def preflight(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-run validation that the frontend can call on-mount to decide
    whether to enable the Run button. Returns `{ok, errors, warnings, ...}`.

    `errors` are hard blockers (Run button disabled until fixed).
    `warnings` are soft (phase will be skipped but other phases can run).
    """
    from backend.workers.agent_tasks import _build_config
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        return {
            "ok": False,
            "errors": ["Profile not found — complete onboarding first."],
            "warnings": [],
        }

    errors: list[str] = []
    warnings: list[str] = []
    if not profile.resume_url:
        errors.append("Resume not uploaded.")

    try:
        config = _build_config(user, profile)
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"Config build failed: {type(e).__name__}: {str(e)[:200]}"],
            "warnings": [],
        }

    prefs = _ensure_dict(profile.job_preferences)
    if not prefs.get("keywords") and not prefs.get("job_titles"):
        errors.append("No job titles or keywords set in your preferences.")

    creds = _ensure_dict(profile.platform_passwords)
    for platform in ["linkedin", "internshala", "wellfound", "naukri", "unstop"]:
        nested = creds.get(platform)
        if isinstance(nested, dict) and nested.get("email") and nested.get("password"):
            continue
        warnings.append(f"{platform}: no credentials (that phase will be skipped).")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "role_agents_count": len(config.get("role_agents", [])),
        "keywords_count": len(config.get("keywords", [])),
        "resume_uploaded": bool(profile.resume_url),
    }


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
        prefs_dict = _ensure_dict(profile.job_preferences)
        schedule = prefs_dict.get("schedule", schedule)

    return schedule

async def _owned_run_or_404(db: AsyncSession, run_id: str, user: User) -> AgentRun:
    """Fetch a run and assert it belongs to the requesting user.

    Without this, the run-log endpoints leaked logs across tenants (IDOR / OWASP
    A01) because they queried AgentLog by run_id alone.
    """
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == uuid.UUID(run_id),
            AgentRun.user_id == user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/runs/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.models.agent_run import AgentLog
    await _owned_run_or_404(db, run_id, user)
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
    user: User = Depends(require_plan("pro")),
    db: AsyncSession = Depends(get_db),
):
    # This endpoint spends the operator's system Gemini key. Two guards (audit M6):
    #   1. Pro-plan only (via require_plan above) — shrinks the abuse surface.
    #   2. Per-user daily cap so a single account can't drain operator LLM budget.
    from backend.models.agent_run import AgentLog
    from backend.models.profile import UserProfile
    from backend.services.rate_limits import default_limiter

    _ok, _reason = default_limiter.can_apply(str(user.id), "analyze")
    if not _ok:
        raise HTTPException(429, detail=f"Analyze rate limit: {_reason}")

    await _owned_run_or_404(db, run_id, user)
    result = await db.execute(
        select(AgentLog).where(
            AgentLog.run_id == uuid.UUID(run_id),
            AgentLog.event_type == "error"
        ).order_by(AgentLog.created_at)
    )
    error_logs = result.scalars().all()
    if not error_logs:
        return {"message": "No errors to analyze in this run.", "advice": None}
        
    errors_text = "\n".join([f"- {log.message}" for log in error_logs[:30]])

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.system_gemini_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""You are an AI agent coach for a job auto-applier.

The agent ran and produced these error log lines:
{errors_text}

Produce 1-3 **actionable rules** the agent's form-filling / navigation LLM should follow in future runs to avoid repeating these failures.

FORMAT each rule as a single imperative sentence. Examples of good rules:
- "When a dropdown has no exact match, pick the closest option instead of leaving it blank."
- "Skip jobs that require > 5 years experience when the candidate has < 2."
- "If the 'Next' button is not visible, scroll down before retrying."
- "Answer 'Are you authorized to work in India?' with 'Yes' for Indian candidates."
- "When cover letter is required but the text box is pre-filled, do NOT overwrite it."

BAD rules (too vague — do NOT produce these):
- "Be more careful with form fields."
- "Handle errors better."

Output ONLY the rules, one per line, no numbering, no extra commentary."""
        response = model.generate_content(prompt)
        advice = response.text.strip()
        default_limiter.register_apply(str(user.id), "analyze")  # count toward daily cap

        # Save to profile
        prof_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = prof_result.scalar_one_or_none()
        if profile:
            prefs = _ensure_dict(profile.job_preferences)
            existing = prefs.get("agent_custom_instructions", "")
            if advice not in existing:
                prefs["agent_custom_instructions"] = f"{existing}\n{advice}".strip()
            profile.job_preferences = prefs
            await db.commit()
            
        return {"message": "Analyzed successfully", "advice": advice}
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")
