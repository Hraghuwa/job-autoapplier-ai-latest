from typing import Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models.user import User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[settings.algorithm]
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise exc
        # Audit M1: a refresh token must not be usable as an access token.
        # Legacy tokens (no "type" claim) are still accepted during rollout.
        if payload.get("type") == "refresh":
            raise exc
    except JWTError:
        raise exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise exc
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_plan(plan: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        order = {"free": 0, "pro": 1, "team": 2}
        if order.get(user.plan, 0) < order.get(plan, 1):
            raise HTTPException(
                status_code=402,
                detail=f"This feature requires the {plan} plan. Upgrade at /settings/billing",
            )
        return user
    return _check
