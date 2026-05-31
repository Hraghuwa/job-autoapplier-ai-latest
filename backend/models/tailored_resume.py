"""SQLAlchemy model for cached tailored resumes.

One row per (user_id, jd_hash, profile_ver). The unique constraint guarantees
the store's "build once, reuse forever" semantics survive concurrent writes.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Dict

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "jd_hash", "profile_ver",
                         name="uq_tailored_user_jd_ver"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jd_hash:      Mapped[str]            = mapped_column(String(64), index=True)
    jd_signature: Mapped[Optional[Dict]] = mapped_column(JSONB)
    resume_json:  Mapped[Optional[Dict]] = mapped_column(JSONB)
    pdf_path:     Mapped[str]            = mapped_column(String(1024))
    model_used:   Mapped[Optional[str]]  = mapped_column(String(255))
    profile_ver:  Mapped[int]            = mapped_column(Integer, default=1)
    jd_coverage:  Mapped[Optional[float]] = mapped_column(Float)
    created_at:   Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)
