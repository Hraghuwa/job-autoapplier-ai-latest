from typing import Optional, List
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import require_admin
from backend.models.user import User, PlanEnum
from backend.models.agent_run import AgentRun, RunStatus
from backend.models.payment import Payment
from backend.schemas.auth import UserOut

router = APIRouter()


@router.get("/users", response_model=List[UserOut])
async def admin_users(
    plan: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(User)
    if plan:
        q = q.where(User.plan == plan)
    q = q.order_by(desc(User.created_at)).limit(limit)
    result = await db.execute(q)
    return [UserOut.model_validate(u) for u in result.scalars().all()]


class PlanOverride(BaseModel):
    plan: str


@router.patch("/users/{user_id}/plan")
async def override_plan(
    user_id: str,
    body: PlanOverride,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    try:
        target.plan = PlanEnum(body.plan)
    except ValueError:
        raise HTTPException(400, f"Invalid plan: {body.plan}")
    await db.commit()
    return {"message": f"Plan set to {body.plan}"}


@router.post("/impersonate/{user_id}")
async def impersonate(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    from backend.routers.auth import create_tokens
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    tokens = create_tokens(str(target.id))
    return {"user": UserOut.model_validate(target), **tokens.model_dump()}


@router.get("/revenue")
async def revenue(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(func.sum(Payment.amount)).where(Payment.status == "paid")
    )
    total_paise = r.scalar() or 0
    r2 = await db.execute(select(func.count()).where(User.plan == "pro"))
    pro_users = r2.scalar() or 0
    r3 = await db.execute(select(func.count(User.id)))
    total_users = r3.scalar() or 0
    return {
        "total_revenue_inr": total_paise / 100,
        "pro_users": pro_users,
        "total_users": total_users,
        "mrr_inr": pro_users * 499,
    }


@router.get("/agents/active")
async def active_agents(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun).where(AgentRun.status == RunStatus.running).limit(50)
    )
    runs = result.scalars().all()
    return [{"run_id": str(r.id), "user_id": str(r.user_id),
             "phase": r.phase, "started_at": r.started_at} for r in runs]


@router.get("/platform-health")
async def platform_health(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun.platform, AgentRun.status, func.count())
        .group_by(AgentRun.platform, AgentRun.status)
    )
    rows = result.all()
    health = {}
    for platform, status, count in rows:
        if platform not in health:
            health[platform] = {"completed": 0, "failed": 0}
        if status == "completed":
            health[platform]["completed"] += count
        elif status == "failed":
            health[platform]["failed"] += count
    for p, h in health.items():
        total = h["completed"] + h["failed"]
        h["success_rate"] = round(h["completed"] / total * 100 if total else 0, 1)
    return health


@router.get("/metrics")
async def metrics(
    days: int = 30,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Observability snapshot (audit §6c): per-platform success rates, apply
    volume, latency p50/p95, and login-challenge counts over the last `days`.
    The math lives in services/run_metrics.compute_metrics (pure + unit-tested);
    this endpoint just feeds it rows.
    """
    from datetime import datetime, timedelta
    from backend.models.agent_run import AgentLog
    from backend.services.run_metrics import compute_metrics

    days = max(1, min(int(days or 30), 365))
    cutoff = datetime.utcnow() - timedelta(days=days)

    runs_res = await db.execute(
        select(AgentRun).where(AgentRun.started_at >= cutoff)
    )
    runs = runs_res.scalars().all()

    # login_challenge counts per platform, joined through the run.
    ch_res = await db.execute(
        select(AgentRun.platform, func.count())
        .join(AgentLog, AgentLog.run_id == AgentRun.id)
        .where(AgentLog.event_type == "login_challenge",
               AgentRun.started_at >= cutoff)
        .group_by(AgentRun.platform)
    )
    challenge_counts = {str(p or "unknown"): int(c) for p, c in ch_res.all()}

    out = compute_metrics(runs, challenge_counts=challenge_counts)
    out["window_days"] = days
    return out
