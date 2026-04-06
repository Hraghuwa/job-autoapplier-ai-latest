from typing import Optional
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class ReferralStatus(str, PyEnum):
    pending = "pending"
    rewarded = "rewarded"


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referred_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus), default=ReferralStatus.pending
    )
    rewarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    referrer: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[referrer_id], back_populates="referrals_sent"
    )
