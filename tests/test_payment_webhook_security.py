"""Webhook security: a forged payment must NOT upgrade a plan when the webhook
secret is unconfigured. Both webhooks must FAIL CLOSED (the bug let anyone POST
checkout.session.completed with a user_id and get a free Pro upgrade)."""
import json
import pytest
from fastapi.testclient import TestClient

import backend.main as m
from backend.config import settings


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "", raising=False)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "", raising=False)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x", raising=False)
    return TestClient(m.app)


def test_stripe_webhook_refused_without_secret(client):
    forged = {"type": "checkout.session.completed",
              "data": {"object": {"id": "s1", "metadata": {"plan_id": "pro", "user_id": "x"}}}}
    r = client.post("/payments/stripe/webhook", content=json.dumps(forged))
    assert r.status_code == 503   # refused, NOT processed → no free upgrade


def test_razorpay_webhook_refused_without_secret(client):
    r = client.post("/payments/razorpay/webhook", content=json.dumps({"event": "payment.failed"}))
    assert r.status_code == 503
