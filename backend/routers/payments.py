from typing import Optional
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User, PlanEnum
from backend.models.payment import Payment, PaymentStatus
from backend.config import settings
from backend.services.plan_gate import PLAN_LIMITS

router = APIRouter()

# ── Plan catalogue ────────────────────────────────────────────────────────────
# amount in paise (₹1 = 100 paise)
PLANS = {
    "pro_monthly": {
        "amount": 49900, "plan": "pro", "period": "month",
        "label": "Pro Monthly", "ai_tokens": 2000, "apply_credits": None,
    },
    "pro_annual": {
        "amount": 399900, "plan": "pro", "period": "year",
        "label": "Pro Annual", "ai_tokens": 2000, "apply_credits": None,
    },
    "credits_100": {
        "amount": 19900, "plan": None, "period": "one-time",
        "label": "100 Credits Pack", "ai_tokens": 0, "apply_credits": 100,
    },
    "credits_500": {
        "amount": 79900, "plan": None, "period": "one-time",
        "label": "500 Credits Pack", "ai_tokens": 0, "apply_credits": 500,
    },
    "tokens_500": {
        "amount": 29900, "plan": None, "period": "one-time",
        "label": "500 AI Token Pack", "ai_tokens": 500, "apply_credits": 0,
    },
}


@router.get("/plans")
async def list_plans():
    return [
        {
            "id": k,
            "name": v.get("label", k.replace("_", " ").title()),
            "amount": v["amount"],
            "currency": "INR",
            "plan": v["plan"],
            "period": v.get("period"),
            "ai_tokens": v.get("ai_tokens", 0),
            "apply_credits": v.get("apply_credits"),
        }
        for k, v in PLANS.items()
    ]


class OrderRequest(BaseModel):
    plan_id: str


class VerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str


@router.post("/create-order")
async def create_order(
    body: OrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = PLANS.get(body.plan_id)
    if not plan:
        raise HTTPException(400, "Unknown plan")

    if not settings.razorpay_key_id:
        raise HTTPException(503, "Payments not configured. Set RAZORPAY_KEY_ID in .env")

    import razorpay
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    order = client.order.create({
        "amount": plan["amount"],
        "currency": "INR",
        "notes": {"user_id": str(user.id), "plan_id": body.plan_id},
    })

    payment = Payment(
        id=uuid.uuid4(),
        user_id=user.id,
        razorpay_order_id=order["id"],
        amount=plan["amount"],
        plan=plan["plan"],
        plan_period=plan.get("period"),
        credits_purchased=plan.get("credits"),
        status=PaymentStatus.created,
    )
    db.add(payment)
    return {"order_id": order["id"], "amount": plan["amount"], "currency": "INR",
            "key_id": settings.razorpay_key_id}


@router.post("/verify")
async def verify_payment(
    body: VerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify HMAC signature
    message = f"{body.razorpay_order_id}|{body.razorpay_payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(400, "Invalid payment signature")

    plan_info = PLANS.get(body.plan_id, {})

    result = await db.execute(
        select(Payment).where(Payment.razorpay_order_id == body.razorpay_order_id)
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.razorpay_payment_id = body.razorpay_payment_id
        payment.status = PaymentStatus.paid

    # Upgrade user plan + award tokens / credits
    if plan_info.get("plan") == "pro":
        user.plan = PlanEnum.pro
        # Reset monthly AI token balance to pro limit
        user.ai_tokens_balance = PLAN_LIMITS["pro"]["ai_tokens_monthly"]
        user.tokens_reset_at = datetime.utcnow() + timedelta(days=30)

    # Top-up apply credits (credits packs)
    extra_credits = plan_info.get("apply_credits") or 0
    if extra_credits:
        user.apply_credits_balance = (user.apply_credits_balance or 0) + extra_credits

    # Top-up AI tokens (token packs)
    extra_tokens = plan_info.get("ai_tokens") or 0
    if extra_tokens and plan_info.get("plan") != "pro":  # pro already set above
        user.ai_tokens_balance = (user.ai_tokens_balance or 0) + extra_tokens

    await db.commit()
    return {
        "message": "Payment verified. Plan upgraded!",
        "plan": user.plan,
        "ai_tokens_balance": user.ai_tokens_balance,
        "apply_credits_balance": user.apply_credits_balance,
    }


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Razorpay webhook events (payment.failed, etc.)"""
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")

    if settings.razorpay_webhook_secret:
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(400, "Invalid webhook signature")

    import json
    event = json.loads(body)
    if event.get("event") == "payment.failed":
        order_id = event.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id")
        if order_id:
            r = await db.execute(select(Payment).where(Payment.razorpay_order_id == order_id))
            payment = r.scalar_one_or_none()
            if payment:
                payment.status = PaymentStatus.failed

    return {"status": "ok"}
