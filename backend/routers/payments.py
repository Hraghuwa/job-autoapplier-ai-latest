"""Payments router — Razorpay (INR) + Stripe (USD/global)."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.payment import Payment, PaymentStatus
from backend.models.user import PlanEnum, User
from backend.config import settings
from backend.services.plan_gate import PLAN_LIMITS

router = APIRouter()

# ── Plan catalogue ────────────────────────────────────────────────────────────
# Razorpay amounts in paise (₹1 = 100 paise)
# Stripe amounts in cents ($1 = 100 cents)
PLANS = {
    "pro_monthly": {
        "label": "Pro Monthly", "plan": "pro", "period": "month",
        "razorpay_amount": 49900, "stripe_amount": 999, "stripe_currency": "usd",
        "ai_tokens": 2000, "apply_credits": None,
    },
    "pro_annual": {
        "label": "Pro Annual", "plan": "pro", "period": "year",
        "razorpay_amount": 399900, "stripe_amount": 7999, "stripe_currency": "usd",
        "ai_tokens": 2000, "apply_credits": None,
    },
    "credits_100": {
        "label": "100 Apply Credits", "plan": None, "period": "one-time",
        "razorpay_amount": 19900, "stripe_amount": 399, "stripe_currency": "usd",
        "ai_tokens": 0, "apply_credits": 100,
    },
    "credits_500": {
        "label": "500 Apply Credits", "plan": None, "period": "one-time",
        "razorpay_amount": 79900, "stripe_amount": 1499, "stripe_currency": "usd",
        "ai_tokens": 0, "apply_credits": 500,
    },
    "tokens_500": {
        "label": "500 AI Tokens", "plan": None, "period": "one-time",
        "razorpay_amount": 29900, "stripe_amount": 599, "stripe_currency": "usd",
        "ai_tokens": 500, "apply_credits": 0,
    },
}


@router.get("/plans")
async def list_plans():
    return [
        {
            "id": k,
            "label": v["label"],
            "plan": v["plan"],
            "period": v["period"],
            "razorpay_amount": v["razorpay_amount"],
            "razorpay_currency": "INR",
            "stripe_amount": v["stripe_amount"],
            "stripe_currency": v.get("stripe_currency", "usd"),
            "ai_tokens": v.get("ai_tokens", 0),
            "apply_credits": v.get("apply_credits"),
        }
        for k, v in PLANS.items()
    ]


@router.get("/config")
async def payment_config():
    """Return public payment keys for the frontend."""
    return {
        "razorpay_available": bool(settings.razorpay_key_id),
        "stripe_available": bool(settings.stripe_secret_key),
        "stripe_publishable_key": settings.stripe_publishable_key or "",
    }


# ── Razorpay ─────────────────────────────────────────────────────────────────

class RazorpayOrderRequest(BaseModel):
    plan_id: str


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str


@router.post("/razorpay/create-order")
async def razorpay_create_order(
    body: RazorpayOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = PLANS.get(body.plan_id)
    if not plan:
        raise HTTPException(400, "Unknown plan")
    if not settings.razorpay_key_id:
        raise HTTPException(503, "Razorpay not configured — set RAZORPAY_KEY_ID")

    import razorpay
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    order = client.order.create({
        "amount": plan["razorpay_amount"],
        "currency": "INR",
        "notes": {"user_id": str(user.id), "plan_id": body.plan_id},
    })

    payment = Payment(
        id=uuid.uuid4(),
        user_id=user.id,
        gateway="razorpay",
        razorpay_order_id=order["id"],
        amount=plan["razorpay_amount"],
        currency="INR",
        plan=plan["plan"],
        plan_period=plan.get("period"),
        status=PaymentStatus.created,
    )
    db.add(payment)
    return {
        "order_id": order["id"],
        "amount": plan["razorpay_amount"],
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
    }


@router.post("/razorpay/verify")
async def razorpay_verify(
    body: RazorpayVerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Fail closed: with an empty secret anyone can compute a "valid" HMAC.
    if not settings.razorpay_key_secret:
        raise HTTPException(503, "Razorpay not configured")
    message = f"{body.razorpay_order_id}|{body.razorpay_payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(400, "Invalid payment signature")

    # The order must be one WE created for THIS user and not yet redeemed.
    # FOR UPDATE serialises concurrent replays of the same signature.
    result = await db.execute(
        select(Payment).where(
            Payment.razorpay_order_id == body.razorpay_order_id,
            Payment.user_id == user.id,
            Payment.gateway == "razorpay",
        ).with_for_update()
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Order not found")
    if payment.status != PaymentStatus.created:
        raise HTTPException(409, "Order already processed")

    # Grant what was PAID for (amount fixed server-side at order creation),
    # never the client-supplied plan_id.
    plan_id = _plan_id_for_amount("razorpay_amount", payment.amount)
    if not plan_id:
        raise HTTPException(400, "Order does not match a known plan")

    payment.razorpay_payment_id = body.razorpay_payment_id
    payment.status = PaymentStatus.paid
    await _apply_plan(user, PLANS[plan_id])
    await db.commit()
    return {
        "message": "Payment verified — plan upgraded!",
        "plan": user.plan,
        "ai_tokens_balance": user.ai_tokens_balance,
        "apply_credits_balance": user.apply_credits_balance,
    }


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    # Fail closed: an unverifiable webhook must not mutate payment state.
    if not settings.razorpay_webhook_secret:
        raise HTTPException(503, "Razorpay webhook secret not configured — refusing unverified webhook")
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(400, "Invalid webhook signature")

    event = json.loads(body)
    if event.get("event") == "payment.failed":
        order_id = (
            event.get("payload", {})
            .get("payment", {})
            .get("entity", {})
            .get("order_id")
        )
        if order_id:
            r = await db.execute(
                select(Payment).where(Payment.razorpay_order_id == order_id)
            )
            p = r.scalar_one_or_none()
            if p:
                p.status = PaymentStatus.failed
    return {"status": "ok"}


# ── Stripe ────────────────────────────────────────────────────────────────────

class StripeSessionRequest(BaseModel):
    plan_id: str
    success_url: str
    cancel_url: str


@router.post("/stripe/create-session")
async def stripe_create_session(
    body: StripeSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = PLANS.get(body.plan_id)
    if not plan:
        raise HTTPException(400, "Unknown plan")
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe not configured — set STRIPE_SECRET_KEY")

    import stripe as stripe_lib
    stripe_lib.api_key = settings.stripe_secret_key

    session = stripe_lib.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": plan.get("stripe_currency", "usd"),
                "unit_amount": plan["stripe_amount"],
                "product_data": {"name": plan["label"]},
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=body.success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=body.cancel_url,
        customer_email=user.email,
        metadata={"user_id": str(user.id), "plan_id": body.plan_id},
    )

    payment = Payment(
        id=uuid.uuid4(),
        user_id=user.id,
        gateway="stripe",
        stripe_session_id=session.id,
        amount=plan["stripe_amount"],
        currency=plan.get("stripe_currency", "usd").upper(),
        plan=plan["plan"],
        plan_period=plan.get("period"),
        status=PaymentStatus.created,
    )
    db.add(payment)
    await db.commit()
    return {"session_id": session.id, "url": session.url}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe sends checkout.session.completed on successful payment."""
    # FAIL CLOSED: without the webhook secret we cannot verify authenticity, and
    # this endpoint grants plan upgrades from the payload. Processing an
    # unverified body would let anyone POST a forged "payment completed" and
    # upgrade any account to Pro for free. Refuse rather than trust it.
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook secret not configured — refusing unverified webhook")
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe not configured")

    import stripe as stripe_lib
    stripe_lib.api_key = settings.stripe_secret_key

    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(
            body, sig, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(400, "Invalid Stripe webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        metadata = session.get("metadata", {})
        plan_id = metadata.get("plan_id", "")
        user_id = metadata.get("user_id", "")

        r = await db.execute(
            select(Payment).where(Payment.stripe_session_id == session_id).with_for_update()
        )
        payment = r.scalar_one_or_none()
        # Idempotent: Stripe redelivers events, so grant only on the first
        # delivery for a session we created, and only once money has moved.
        if (payment is None or payment.status != PaymentStatus.created
                or session.get("payment_status") != "paid"
                or str(payment.user_id) != user_id
                or PLANS.get(plan_id, {}).get("stripe_amount") != payment.amount):
            return {"status": "ignored"}

        payment.stripe_payment_intent_id = session.get("payment_intent")
        payment.status = PaymentStatus.paid

        from backend.models.user import User as UserModel
        ur = await db.execute(
            select(UserModel).where(UserModel.id == payment.user_id)
        )
        u = ur.scalar_one_or_none()
        if u:
            await _apply_plan(u, PLANS[plan_id])

        await db.commit()

    return {"status": "ok"}


# ── Backwards-compat aliases (old frontend calls /payments/create-order) ─────

class OrderRequest(BaseModel):
    plan_id: str


@router.post("/create-order")
async def create_order_alias(
    body: OrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy alias → Razorpay."""
    return await razorpay_create_order(
        RazorpayOrderRequest(plan_id=body.plan_id), user, db
    )


class VerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str


@router.post("/verify")
async def verify_alias(
    body: VerifyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy alias → Razorpay verify."""
    return await razorpay_verify(
        RazorpayVerifyRequest(**body.model_dump()), user, db
    )


# ── Shared plan-application logic ─────────────────────────────────────────────

def _plan_id_for_amount(field: str, amount: int) -> Optional[str]:
    """Map a server-recorded order amount back to its catalogue entry."""
    matches = [k for k, v in PLANS.items() if v[field] == amount]
    return matches[0] if len(matches) == 1 else None


# Amount → plan lookup above requires unique prices per gateway.
for _f in ("razorpay_amount", "stripe_amount"):
    assert len({v[_f] for v in PLANS.values()}) == len(PLANS), f"duplicate {_f} in PLANS"


async def _apply_plan(user: User, plan_info: dict) -> None:
    if plan_info.get("plan") == "pro":
        user.plan = PlanEnum.pro
        user.ai_tokens_balance = PLAN_LIMITS["pro"]["ai_tokens_monthly"]
        user.tokens_reset_at = datetime.utcnow() + timedelta(days=30)

    extra_credits = plan_info.get("apply_credits") or 0
    if extra_credits:
        user.apply_credits_balance = (user.apply_credits_balance or 0) + extra_credits

    extra_tokens = plan_info.get("ai_tokens") or 0
    if extra_tokens and plan_info.get("plan") != "pro":
        user.ai_tokens_balance = (user.ai_tokens_balance or 0) + extra_tokens
