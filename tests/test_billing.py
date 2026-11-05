"""Billing contracts: auth gates, webhook signature, entitlement writes.

Stripe and Supabase are stubbed; no network, no real charges.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.accounts import AccountSession


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _verified_account(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(request: Any, response: Any = None, require_verified: bool = False):
        return AccountSession(
            user_id="11111111-1111-1111-1111-111111111111",
            email="creator@example.test",
            email_verified=True,
            access_token="access",
            session_id=None,
        )

    monkeypatch.setattr("src.api.billing.resolve_account", fake_resolve)


def _install_fake_stripe(monkeypatch: pytest.MonkeyPatch, calls: dict[str, Any]) -> None:
    stripe = types.ModuleType("stripe")
    stripe.api_key = ""

    class FakeSession:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            calls["checkout"] = kwargs
            return types.SimpleNamespace(url="https://checkout.stripe.test/session")

    class FakePortalSession:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            calls["portal"] = kwargs
            return types.SimpleNamespace(url="https://billing.stripe.test/portal")

    stripe.checkout = types.SimpleNamespace(Session=FakeSession)
    stripe.billing_portal = types.SimpleNamespace(Session=FakePortalSession)

    def construct_event(payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        calls["webhook"] = {"payload": payload, "signature": signature, "secret": secret}
        if signature != "valid-signature":
            raise ValueError("bad signature")
        return calls["event"]

    stripe.Webhook = types.SimpleNamespace(construct_event=construct_event)
    monkeypatch.setitem(sys.modules, "stripe", stripe)


def test_checkout_requires_signin(client: TestClient) -> None:
    response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
    assert response.status_code == 401


def test_checkout_creates_session_for_verified_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _verified_account(monkeypatch)
    calls: dict[str, Any] = {}
    _install_fake_stripe(monkeypatch, calls)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
    finally:
        get_settings.cache_clear()
    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("https://checkout.stripe.test/")
    assert calls["checkout"]["mode"] == "subscription"
    assert calls["checkout"]["line_items"] == [{"price": "price_growth", "quantity": 1}]
    assert calls["checkout"]["metadata"]["plan"] == "growth"


def test_checkout_rejects_unknown_plan(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _verified_account(monkeypatch)
    response = client.post("/api/v1/billing/checkout", json={"plan": "enterprise"})
    assert response.status_code == 422


def test_webhook_rejects_bad_signature(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {"event": {}}
    _install_fake_stripe(monkeypatch, calls)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_123")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "bogus"},
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 400


def test_webhook_completed_grants_plan(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {
        "event": {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "plan": "growth",
                        "user_id": "11111111-1111-1111-1111-111111111111",
                    },
                    "client_reference_id": "11111111-1111-1111-1111-111111111111",
                    "customer": "cus_123",
                }
            },
        }
    }
    _install_fake_stripe(monkeypatch, calls)
    rpc_calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
        rpc_calls.append((name, params))
        return {"allowed": True}

    from src.clients import supabase as supabase_module

    monkeypatch.setattr(
        supabase_module.SupabaseClient, "rpc", lambda self, name, params: fake_rpc(name, params)
    )
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_123")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "valid-signature"},
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 200, response.text
    assert rpc_calls == [
        (
            "muse_set_plan",
            {
                "p_user_id": "11111111-1111-1111-1111-111111111111",
                "p_plan": "growth",
                "p_stripe_customer_id": "cus_123",
            },
        )
    ]
