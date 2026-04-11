from typing import Dict, List, Optional
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class ApplicationStatus(str, PyEnum):
    applied = "applied"
    viewed = "viewed"
    shortlisted = "shortlisted"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    platform: Mapped[str] = mapped_column(String(50))
    job_title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    job_url: Mapped[Optional[str]] = mapped_column(String(1024))
    jd_text: Mapped[Optional[str]] = mapped_column(Text)
    job_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256 dedup key
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))

    # Gemini match scoring
    match_score: Mapped[Optional[int]] = mapped_column(Integer)
    match_reason: Mapped[Optional[str]] = mapped_column(Text)
    matched_skills: Mapped[Optional[List]] = mapped_column(JSONB)
    missing_skills: Mapped[Optional[List]] = mapped_column(JSONB)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.applied
    )
    cover_letter_used: Mapped[Optional[str]] = mapped_column(Text)
    interview_prep: Mapped[Optional[Dict]] = mapped_column(JSONB)

    history: Mapped[Optional[List[Dict]]] = mapped_column(JSONB, default=list) # Activity log
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="applications")  # noqa: F821
    outcome: Mapped[Optional["JobOutcome"]] = relationship(
        back_populates="application", uselist=False, cascade="all, delete-orphan"
    )


class JobOutcome(Base):
    """ML flywheel — captures final outcome per application for future model training."""

    __tablename__ = "job_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), unique=True
    )
    outcome: Mapped[Optional[str]] = mapped_column(String(50))
    outcome_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    jd_keywords: Mapped[Optional[List]] = mapped_column(JSONB)
    resume_skills: Mapped[Optional[List]] = mapped_column(JSONB)

    application: Mapped["Application"] = relationship(back_populates="outcome")
