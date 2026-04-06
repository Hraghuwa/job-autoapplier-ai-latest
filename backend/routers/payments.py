from typing import Optional
import uuid
import hmac
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User, PlanEnum
from backend.models.payment import Payment, PaymentStatus
from backend.config import settings

router = APIRouter()

PLANS = {
    "pro_monthly":  {"amount": 49900,  "plan": "pro",  "period": "monthly"},
    "pro_annual":   {"amount": 399900, "plan": "pro",  "period": "annual"},
    "credits_100":  {"amount": 19900,  "plan": "free", "period": "credits", "credits": 100},
}


@router.get("/plans")
async def list_plans():
    return [
        {"id": k, "name": k.replace("_", " ").title(),
         "amount": v["amount"], "currency": "INR",
         "plan": v["plan"], "period": v.get("period")}
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

    # Upgrade user plan
    if plan_info.get("plan") == "pro":
        user.plan = PlanEnum.pro

    return {"message": "Payment verified. Plan upgraded!", "plan": user.plan}


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
