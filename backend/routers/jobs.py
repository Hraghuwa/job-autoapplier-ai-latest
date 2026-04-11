from typing import Optional, List
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.application import Application, ApplicationStatus
from backend.schemas.application import ApplicationOut, ApplicationDetail, StatusUpdate, AnalyticsOut
from backend.services.tracking_service import tracking_service

router = APIRouter()


@router.get("", response_model=List[ApplicationOut])
async def list_jobs(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Application).where(Application.user_id == user.id)
    if platform:
        q = q.where(Application.platform == platform)
    if status:
        q = q.where(Application.status == status)
    if min_score is not None:
        q = q.where(Application.match_score >= min_score)
    if max_score is not None:
        q = q.where(Application.match_score <= max_score)
    q = q.order_by(desc(Application.applied_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    apps = result.scalars().all()
    return [ApplicationOut.model_validate(a) for a in apps]


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_r = await db.execute(select(func.count()).where(Application.user_id == user.id))
    total = total_r.scalar() or 0

    week_r = await db.execute(select(func.count()).where(
        Application.user_id == user.id, Application.applied_at >= week_ago))
    this_week = week_r.scalar() or 0

    month_r = await db.execute(select(func.count()).where(
        Application.user_id == user.id, Application.applied_at >= month_ago))
    this_month = month_r.scalar() or 0

    # By platform
    plat_r = await db.execute(
        select(Application.platform, func.count())
        .where(Application.user_id == user.id)
        .group_by(Application.platform)
    )
    by_platform = {row[0]: row[1] for row in plat_r.all()}

    # By status
    stat_r = await db.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user.id)
        .group_by(Application.status)
    )
    by_status = {str(row[0]): row[1] for row in stat_r.all()}

    # Response rate (shortlisted + interview + offer / total)
    positive = sum(by_status.get(s, 0) for s in ["shortlisted", "interview", "offer"])
    response_rate = round((positive / total * 100) if total else 0, 1)

    # Top companies
    comp_r = await db.execute(
        select(Application.company, func.count())
        .where(Application.user_id == user.id)
        .group_by(Application.company)
        .order_by(desc(func.count()))
        .limit(5)
    )
    top_companies = [row[0] for row in comp_r.all()]

    # Avg match score
    avg_r = await db.execute(
        select(func.avg(Application.match_score))
        .where(Application.user_id == user.id, Application.match_score.isnot(None))
    )
    avg_match = avg_r.scalar()
    avg_match_score = round(float(avg_match), 1) if avg_match else None

    # Daily applies (last 30 days)
    daily_r = await db.execute(
        select(
            func.date(Application.applied_at).label("day"),
            func.count().label("count"),
        )
        .where(Application.user_id == user.id, Application.applied_at >= month_ago)
        .group_by(func.date(Application.applied_at))
        .order_by(func.date(Application.applied_at))
    )
    daily_applies = [{"date": str(row.day), "count": row.count} for row in daily_r.all()]

    return AnalyticsOut(
        total=total, total_applied=total,
        this_week=this_week, this_month=this_month,
        by_platform=by_platform, by_status=by_status,
        response_rate=response_rate, top_companies=top_companies,
        avg_match_score=avg_match_score, daily_applies=daily_applies,
    )


@router.get("/{job_id}", response_model=ApplicationDetail)
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(
            Application.id == uuid.UUID(job_id),
            Application.user_id == user.id,
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Job not found")
    return ApplicationDetail.model_validate(app)


@router.patch("/{job_id}/status", response_model=ApplicationOut)
async def update_status(
    job_id: str,
    body: StatusUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(
            Application.id == uuid.UUID(job_id),
            Application.user_id == user.id,
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Job not found")

    try:
        await tracking_service.update_status(db, app, ApplicationStatus(body.status))
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")

    # Auto-generate interview prep when moving to shortlisted/interview
    if body.status in ("shortlisted", "interview") and not app.interview_prep:
        try:
            from backend.services.gemini_service import generate_interview_prep
            from backend.models.profile import UserProfile
            from sqlalchemy import select as sa_select
            prof_r = await db.execute(sa_select(UserProfile).where(UserProfile.user_id == user.id))
            profile = prof_r.scalar_one_or_none()
            n = 10 if user.plan != "free" else 3
            resume_summary = str(profile.extracted_data or {}) if profile else ""
            app.interview_prep = generate_interview_prep(
                resume_summary, app.jd_text or "", app.company, n_questions=n
            )
        except Exception:
            pass

    await db.commit()
    return ApplicationOut.model_validate(app)


@router.get("/{job_id}/interview-prep")
async def interview_prep(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(
            Application.id == uuid.UUID(job_id),
            Application.user_id == user.id,
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Job not found")

    n = 10 if user.plan != "free" else 3
    prep = app.interview_prep or {}

    if user.plan == "free":
        questions = prep.get("questions", [])[:3]
        remaining = len(prep.get("questions", [])) - 3
        return {
            "questions": questions,
            "company_brief": prep.get("company_brief", ""),
            "red_flags": prep.get("red_flags", []),
            "locked": remaining > 0,
            "locked_count": max(0, remaining),
            "upgrade_message": "Upgrade to Pro to unlock all 10 questions + model answers",
        }

    return prep
