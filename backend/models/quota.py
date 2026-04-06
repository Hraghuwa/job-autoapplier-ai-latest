from typing import Optional
import uuid
import datetime

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class UsageQuota(Base):
    __tablename__ = "usage_quotas"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "quota_date", name="uq_quota_user_platform_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50))
    quota_date: Mapped[datetime.date] = mapped_column(Date)   # renamed from 'date' to avoid shadowing the type
    applies_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="usage_quotas")  # noqa: F821
