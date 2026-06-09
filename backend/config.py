import logging
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # env_file is a local-dev fallback only.
    # On Railway/production, vars come from the platform environment directly.
    model_config = SettingsConfigDict(
        env_file=["backend/.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database — SQLite for local dev, PostgreSQL for production.
    # On Railway: add a PostgreSQL plugin and DATABASE_URL is auto-injected.
    database_url: str = "sqlite+aiosqlite:////tmp/jobagent.db"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = ""
    algorithm: str = "HS256"

    @field_validator("secret_key", mode="before")
    @classmethod
    def secret_key_must_be_set(cls, v):
        if not v or v == "change-me-in-production":
            # Try to derive a stable key from FERNET_KEY so tokens survive
            # restarts even when SECRET_KEY is not explicitly set.
            # FERNET_KEY is already required for credential encryption, so it's
            # always present in production. Deriving from it gives stability
            # without needing a second env var. (Read from the environment
            # directly — in Pydantic v2 a before-validator can't see sibling
            # fields, and FERNET_KEY is always env-provided in production.)
            import os as _os
            seed = _os.environ.get("FERNET_KEY", "")
            if seed:
                import hashlib
                derived = hashlib.sha256(f"jobagent-jwt-{seed}".encode()).hexdigest()
                logger.warning(
                    "SECRET_KEY not set — derived a stable key from FERNET_KEY. "
                    "JWTs will survive restarts but you should set SECRET_KEY "
                    "explicitly in Railway environment variables for full security."
                )
                return derived
            # Last resort: ephemeral. Tokens die on restart.
            ephemeral = secrets.token_hex(32)
            logger.error(
                "SECRET_KEY and FERNET_KEY both unset — using an ephemeral random "
                "key. Users will be logged out on every restart. "
                "Set SECRET_KEY in Railway environment variables NOW."
            )
            return ephemeral
        return v

    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Encryption
    fernet_key: str = ""

    # AI
    system_gemini_key: str = ""

    # Payments — Razorpay (INR)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Payments — Stripe (USD / global)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # Email
    resend_api_key: str = ""

    # App
    frontend_url: str = "http://localhost:3000"
    admin_email: str = ""  # auto-flagged as admin on first signup


settings = Settings()
