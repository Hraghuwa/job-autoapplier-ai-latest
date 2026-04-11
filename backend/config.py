from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import validator


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

    @validator("secret_key")
    def secret_key_must_be_set(cls, v):
        if not v or v == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY not configured in backend/.env — "
                "generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Encryption
    fernet_key: str = ""  # generate: from cryptography.fernet import Fernet; Fernet.generate_key()

    # AI
    system_gemini_key: str = ""

    # Payments
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Email
    resend_api_key: str = ""

    # App
    frontend_url: str = "http://localhost:3000"
    admin_email: str = ""  # auto-flagged as admin on first signup


settings = Settings()
