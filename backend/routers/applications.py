"""Applications router — per-resume and per-archetype response-rate analytics.

Backs the Patterns tab in the UI. Two endpoints:

  GET /applications/response-rates/by-resume    -> [{tailored_resume_id, applied, callbacks, response_rate}]
  GET /applications/response-rates/by-archetype -> [{archetype, applied, callbacks, response_rate}]
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.services import response_rates

router = APIRouter()


@router.get("/response-rates/by-resume")
async def response_rates_by_resume(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-tailored-resume callback rates."""
    # response_rates uses a sync Session API. SQLAlchemy 1.4+/2.0 supports
    # running sync ops via run_sync on the async session's underlying
    # connection — but for simplicity we open a short-lived sync session
    # from the bind URL.
    return _run_sync_query(lambda s: response_rates.by_tailored_resume(s, user.id))


@router.get("/response-rates/by-archetype")
async def response_rates_by_archetype(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-archetype callback rates."""
    return _run_sync_query(lambda s: response_rates.by_archetype(s, user.id))


def _run_sync_query(fn):
    """Open a sync Session against the same URL, run `fn(session)`, close."""
    from backend.workers.agent_tasks import _sync_session
    session = _sync_session()
    try:
        return fn(session)
    finally:
        session.close()
