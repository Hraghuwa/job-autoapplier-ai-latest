import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings

logger = logging.getLogger(__name__)


def _coerce_async_url(url: str) -> str:
    """Railway / Heroku inject DATABASE_URL with the sync driver
    (`postgresql://` or `postgres://`). SQLAlchemy's async engine requires the
    explicit async driver prefix. Coerce to asyncpg so the app starts cleanly
    regardless of how the platform exposes the env var.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


_resolved_url = _coerce_async_url(settings.database_url)
if _resolved_url != settings.database_url:
    logger.warning("Coerced DATABASE_URL to async driver: %s", _resolved_url.split("@")[0] + "@…")

# SQLite needs check_same_thread=False; PostgreSQL ignores connect_args entirely
_connect_args = {"check_same_thread": False} if _resolved_url.startswith("sqlite") else {}

engine = create_async_engine(
    _resolved_url,
    echo=False,
    pool_pre_ping=not _resolved_url.startswith("sqlite"),  # SQLite doesn't support pre-ping
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def db_ping(timeout: float = 3.0) -> bool:
    """Return True iff the database answers a trivial query within `timeout`.

    Used by /health so an unreachable DB (e.g. an expired Railway plan) shows up
    as a clear signal instead of surfacing only as a confusing "login is broken".
    Never raises — any failure (connection refused, auth, timeout) → False.
    """
    async def _q():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_q(), timeout=timeout)
        return True
    except Exception as e:
        logger.warning("db_ping failed: %s: %s", type(e).__name__, e)
        return False
