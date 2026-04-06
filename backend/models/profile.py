from typing import Dict, List, Optional
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Resume
    resume_url: Mapped[Optional[str]] = mapped_column(String(512))
    resume_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    resume_filename: Mapped[Optional[str]] = mapped_column(String(255))
    extracted_data: Mapped[Optional[Dict]] = mapped_column(JSONB)  # Gemini-parsed fields

    # Job preferences & form autofill
    job_preferences: Mapped[Optional[Dict]] = mapped_column(JSONB)
    autofill_bank: Mapped[Optional[Dict]] = mapped_column(JSONB)
    cover_letter: Mapped[Optional[str]] = mapped_column(Text)

    # Encrypted platform credentials (Fernet per-key)
    platform_passwords: Mapped[Optional[Dict]] = mapped_column(JSONB)
    session_cookies: Mapped[Optional[Dict]] = mapped_column(JSONB)

    # Browser stealth
    chrome_profile_path: Mapped[Optional[str]] = mapped_column(String(512))
    fingerprint: Mapped[Optional[Dict]] = mapped_column(JSONB)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="profile")  # noqa: F821
