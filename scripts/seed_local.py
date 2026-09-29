"""Local dev seed — full schema (from the SQLAlchemy models) + the admin login.

Replaces start.sh's hand-rolled raw-SQLite CREATE TABLE, which drifted from the
models (missing columns like users.ai_tokens_balance) and made login 500. Using
Base.metadata.create_all guarantees the schema always matches the models and
works for any DATABASE_URL (SQLite locally, Postgres/Neon in prod).

Idempotent. Self-heals a stale SQLite schema: if `users` exists but lacks a
current column, it drops & recreates (the local /tmp dev DB is ephemeral).

Reads DATABASE_URL from the environment (set by start.sh). Admin creds override
via SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD; defaults match start.sh's banner.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "hraghuwanshi3110@gmail.com")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "JobAgent@2024")
ADMIN_NAME = os.environ.get("SEED_ADMIN_NAME", "Harsh Raghuwanshi")


async def main():
    import backend.models  # noqa: F401 — register all models on Base
    from sqlalchemy import inspect as sa_inspect, select
    from backend.database import engine, AsyncSessionLocal, Base
    from backend.models.user import User, PlanEnum
    from backend.models.profile import UserProfile
    from passlib.context import CryptContext

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def _schema_is_stale(sync_conn) -> bool:
        insp = sa_inspect(sync_conn)
        if "users" not in insp.get_table_names():
            return False  # fresh DB → just create
        cols = {c["name"] for c in insp.get_columns("users")}
        return "ai_tokens_balance" not in cols  # a column the model now requires

    async with engine.begin() as conn:
        if await conn.run_sync(_schema_is_stale):
            print("  stale schema detected — recreating from models")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(
            select(User).where(User.email == ADMIN_EMAIL))).scalar_one_or_none()
        if existing is None:
            user = User(id=uuid.uuid4(), email=ADMIN_EMAIL, name=ADMIN_NAME,
                        hashed_password=pwd.hash(ADMIN_PASSWORD),
                        plan=PlanEnum.pro, is_admin=True)
            db.add(user)
            await db.flush()
            db.add(UserProfile(id=uuid.uuid4(), user_id=user.id))
        else:
            existing.hashed_password = pwd.hash(ADMIN_PASSWORD)
            existing.is_admin = True
        await db.commit()
    print(f"  DB seeded — admin {ADMIN_EMAIL} ready")


if __name__ == "__main__":
    asyncio.run(main())
