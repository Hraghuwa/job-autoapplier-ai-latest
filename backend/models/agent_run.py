from typing import Dict, List, Optional
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class RunStatus(str, PyEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    limit_reached = "limit_reached"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase: Mapped[int] = mapped_column(Integer)
    platform: Mapped[Optional[str]] = mapped_column(String(50))
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    config_snapshot: Mapped[Optional[Dict]] = mapped_column(JSONB)

    user: Mapped["User"] = relationship(back_populates="agent_runs")  # noqa: F821
    logs: Mapped[List["AgentLog"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50))   # applied, skipped, error, info
    message: Mapped[str] = mapped_column(String(2048))
    screenshot_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["AgentRun"] = relationship(back_populates="logs")
