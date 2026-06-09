import secrets
import uuid
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User, PlanEnum
from backend.models.profile import UserProfile
from backend.models.referral import Referral
from backend.schemas.auth import (
    LoginRequest, RegisterRequest, RefreshRequest, TokenResponse, UserOut
)

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    expire = datetime.utcnow() + expires_delta
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": token_type},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def create_tokens(user_id: str) -> TokenResponse:
    access = create_token(user_id, timedelta(minutes=settings.access_token_expire_minutes), "access")
    refresh = create_token(user_id, timedelta(days=settings.refresh_token_expire_days), "refresh")
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Auto-flag admin if:
    #   1. email matches ADMIN_EMAIL env var, OR
    #   2. this is the very first user in the DB (bootstrap admin)
    is_admin = bool(settings.admin_email and body.email == settings.admin_email)
    if not is_admin:
        count_res = await db.execute(select(func.count()).select_from(User))
        if (count_res.scalar() or 0) == 0:
            is_admin = True

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        hashed_password=hash_password(body.password),
        plan=PlanEnum.free,
        is_admin=is_admin,
    )
    db.add(user)

    # Empty profile
    profile = UserProfile(id=uuid.uuid4(), user_id=user.id)
    db.add(profile)

    # Referral code for this user
    ref_code = secrets.token_urlsafe(10)[:12].upper()
    referral = Referral(id=uuid.uuid4(), referrer_id=user.id, code=ref_code)
    db.add(referral)

    # Honor incoming referral code
    if body.referral_code:
        result = await db.execute(
            select(Referral).where(Referral.code == body.referral_code.upper())
        )
        parent_ref = result.scalar_one_or_none()
        if parent_ref:
            parent_ref.referred_id = user.id

    await db.commit()

    # TODO (Step 5a): send welcome email via Resend

    return create_tokens(str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_tokens(str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(body.refresh_token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        # Audit M1: only a refresh token may be exchanged here. Tokens minted
        # before this change have no "type" claim — accept them during rollout.
        token_type = payload.get("type")
        if token_type is not None and token_type != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return create_tokens(user_id)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


# ── Bootstrap admin promotion ────────────────────────────────────────────────
#
# Lets the operator promote any account to admin without redeploying. Two ways
# to authorize:
#   1. ADMIN_EMAIL env var matches the requesting user's email, OR
#   2. ADMIN_BOOTSTRAP_SECRET env var matches the X-Admin-Secret header.
# Without either, returns 403. Useful when you've already signed up but
# forgot to set ADMIN_EMAIL beforehand.
import os as _os
from fastapi import Header


@router.post("/promote-self")
async def promote_self(
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bootstrap_secret = _os.environ.get("ADMIN_BOOTSTRAP_SECRET", "").strip()
    email_match = bool(settings.admin_email and user.email == settings.admin_email)
    secret_match = bool(bootstrap_secret and x_admin_secret == bootstrap_secret)

    if not (email_match or secret_match):
        raise HTTPException(
            status_code=403,
            detail=(
                "Not authorized to self-promote. Set ADMIN_EMAIL to your account "
                "email, or send X-Admin-Secret header matching ADMIN_BOOTSTRAP_SECRET."
            ),
        )

    user.is_admin = True
    await db.commit()
    return {"ok": True, "is_admin": True, "email": user.email}

