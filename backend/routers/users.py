from typing import Optional
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.models.quota import UsageQuota
from backend.models.referral import Referral, ReferralStatus
from backend.schemas.user import ProfileOut, ProfileUpdate, GeminiKeyRequest, UsageOut
from backend.services.plan_gate import PLAN_LIMITS
from backend.services.crypto_service import encrypt

router = APIRouter()


async def _profile(user: User, db: AsyncSession) -> UserProfile:
    r = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(500, "Profile not found")
    return p


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ProfileOut.model_validate(await _profile(user, db))


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _profile(user, db)
    if body.autofill_bank is not None:
        p.autofill_bank = body.autofill_bank
    if body.cover_letter is not None:
        p.cover_letter = body.cover_letter
    if body.job_preferences is not None:
        p.job_preferences = body.job_preferences
    await db.commit()
    return ProfileOut.model_validate(p)


@router.post("/gemini-key")
async def set_gemini_key(
    body: GeminiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate key with a quick test call
    try:
        import google.generativeai as genai
        genai.configure(api_key=body.api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        model.generate_content("Say OK")
    except Exception as e:
        raise HTTPException(400, f"Invalid Gemini API key: {e}")

    user.gemini_key_encrypted = encrypt(body.api_key)
    await db.commit()
    return {"message": "Gemini API key saved and validated"}


@router.get("/usage", response_model=UsageOut)
async def usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = date.today()
    r = await db.execute(
        select(func.sum(UsageQuota.applies_count)).where(
            UsageQuota.user_id == user.id,
            UsageQuota.quota_date == today,
        )
    )
    applies_today = r.scalar() or 0
    plan_str = "free"
    if user.plan:
        plan_str = user.plan.value if hasattr(user.plan, "value") else str(user.plan)
    
    limit_info = PLAN_LIMITS.get(plan_str, PLAN_LIMITS["free"])
    limit = limit_info.get("applies_per_48hr", 20)
    
    return UsageOut(
        tokens_used_today=user.tokens_used_today or 0,
        plan=plan_str,
        applies_today=applies_today,
        applies_limit=limit,
    )


@router.get("/referral")
async def referral_info(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Referral).where(Referral.referrer_id == user.id))
    refs = r.scalars().all()
    my_code = next((ref.code for ref in refs if ref.referred_id is None), None)
    rewarded = sum(1 for ref in refs if ref.status == ReferralStatus.rewarded)
    total_referred = sum(1 for ref in refs if ref.referred_id is not None)
    return {"code": my_code, "total_referred": total_referred, "rewards_earned": rewarded}


@router.delete("/account")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import os, shutil
    # Delete resume files
    upload_dir = os.path.join("uploads", str(user.id))
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    await db.delete(user)  # cascade deletes profile, applications, etc.
    await db.commit()
    return {"message": "Account deleted. Goodbye."}
