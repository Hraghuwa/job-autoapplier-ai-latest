"""Regression tests for the 2026-09 security assessment fixes (real sqlite DB,
in-memory rate limiter, no network)."""
import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import backend.main as m
import backend.models  # noqa: F401
from backend.config import settings
from backend.database import Base, get_db
from backend.models.payment import Payment, PaymentStatus
from backend.services import rate_limits
from backend.services.plan_gate import consume_ai_token

SECRET = "rzp-test-secret"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _init():
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
    asyncio.run(_init())

    async def _db():
        async with Session() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    m.app.dependency_overrides[get_db] = _db
    lim = rate_limits.default_limiter
    monkeypatch.setattr(lim, "_redis", None)
    monkeypatch.setattr(lim, "_resolved", True)
    monkeypatch.setattr(lim, "_memory", rate_limits.RateLimiter())
    monkeypatch.setattr(settings, "razorpay_key_secret", SECRET, raising=False)
    yield TestClient(m.app), Session
    m.app.dependency_overrides.pop(get_db, None)


def _register(client, email):
    r = client.post("/auth/register", json={"name": "t", "email": email, "password": "correct-horse"})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, client.get("/auth/me", headers=h).json()


def _order(Session, user_id, order_id, amount):
    async def _add():
        async with Session() as s:
            s.add(Payment(user_id=user_id, gateway="razorpay", razorpay_order_id=order_id,
                          amount=amount, currency="INR", status=PaymentStatus.created))
            await s.commit()
    asyncio.run(_add())


def _verify(client, h, order_id, plan_id="pro_annual"):
    sig = hmac.new(SECRET.encode(), f"{order_id}|pay_1".encode(), hashlib.sha256).hexdigest()
    return client.post("/payments/razorpay/verify", headers=h, json={
        "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1",
        "razorpay_signature": sig, "plan_id": plan_id})


def test_verify_grants_paid_plan_not_requested_plan_and_rejects_replay(env):
    import uuid
    client, Session = env
    h, me = _register(client, "buyer@example.com")
    _order(Session, uuid.UUID(me["id"]), "order_cheap", 19900)  # credits_100

    r = _verify(client, h, "order_cheap", plan_id="pro_annual")
    assert r.status_code == 200
    assert r.json()["plan"] != "pro"                      # client plan_id ignored
    assert r.json()["apply_credits_balance"] == 20 + 100  # got what was paid for
    assert _verify(client, h, "order_cheap").status_code == 409  # replay refused


def test_verify_rejects_unknown_or_foreign_order_and_empty_secret(env, monkeypatch):
    import uuid
    client, Session = env
    _, victim = _register(client, "victim@example.com")
    h, _ = _register(client, "thief@example.com")
    _order(Session, uuid.UUID(victim["id"]), "order_victim", 49900)

    assert _verify(client, h, "order_never_created").status_code == 404
    assert _verify(client, h, "order_victim").status_code == 404
    monkeypatch.setattr(settings, "razorpay_key_secret", "", raising=False)
    assert _verify(client, h, "order_victim").status_code == 503


def test_signup_never_grants_admin_and_weak_passwords_rejected(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(settings, "admin_email", "ops@example.com", raising=False)
    _, first = _register(client, "first@example.com")      # first user on empty DB
    _, squat = _register(client, "ops@example.com")        # unverified ADMIN_EMAIL
    assert not first["is_admin"] and not squat["is_admin"]
    r = client.post("/auth/register", json={"name": "t", "email": "w@example.com", "password": "a"})
    assert r.status_code == 422


def test_promote_self_requires_bootstrap_secret(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(settings, "admin_email", "ops@example.com", raising=False)
    monkeypatch.setenv("ADMIN_BOOTSTRAP_SECRET", "boot")
    h, _ = _register(client, "ops@example.com")
    assert client.post("/auth/promote-self", headers=h).status_code == 403
    assert client.post("/auth/promote-self", headers={**h, "X-Admin-Secret": "boot"}).status_code == 200


def test_login_throttled_after_repeated_failures(env):
    client, _ = env
    _register(client, "target@example.com")
    codes = [client.post("/auth/login", json={"email": "target@example.com", "password": f"x{i}"}).status_code
             for i in range(rate_limits.PLATFORM_DAILY_CAP["login_fail"] + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {401}


def test_health_does_not_list_user_ids(env):
    client, _ = env
    assert isinstance(client.get("/health").json()["ws_connections"], int)


def test_consume_ai_token_meters_system_key_only():
    u = SimpleNamespace(plan="free", gemini_key_encrypted=None, groq_key_encrypted=None,
                        ai_tokens_balance=1, tokens_reset_at=datetime.utcnow() + timedelta(days=1))
    consume_ai_token(u)
    assert u.ai_tokens_balance == 0
    with pytest.raises(HTTPException) as e:
        consume_ai_token(u)
    assert e.value.status_code == 402
    own = SimpleNamespace(**{**vars(u), "gemini_key_encrypted": "enc"})
    consume_ai_token(own)  # own key → never charged, never blocked
    # Monthly top-up never lowers a purchased balance.
    rich = SimpleNamespace(**{**vars(u), "ai_tokens_balance": 500, "tokens_reset_at": None})
    consume_ai_token(rich)
    assert rich.ai_tokens_balance == 499
