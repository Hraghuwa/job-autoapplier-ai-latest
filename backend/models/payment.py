from typing import Optional
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class PaymentStatus(str, PyEnum):
    created = "created"
    paid = "paid"
    failed = "failed"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Gateway — "razorpay" or "stripe"
    gateway: Mapped[str] = mapped_column(String(20), default="razorpay")

    # Razorpay fields
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(255))
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Stripe fields
    stripe_session_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255))

    amount: Mapped[int] = mapped_column(Integer)        # smallest unit: paise (INR) or cents (USD)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    plan: Mapped[Optional[str]] = mapped_column(String(50))
    plan_period: Mapped[Optional[str]] = mapped_column(String(50))
    credits_purchased: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.created
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="payments")  # noqa: F821
