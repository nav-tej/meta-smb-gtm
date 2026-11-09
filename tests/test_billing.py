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


@pytest.fixture(autouse=True)
def _placeholder_stripe_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every test sees placeholder Stripe settings, never the developer's real .env keys."""
    from src.config import get_settings

    for name, value in {
        "STRIPE_SECRET_KEY": "sk_test_placeholder",
        "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
        "STRIPE_PRICE_STARTER_MONTHLY": "price_starter",
        "STRIPE_PRICE_STARTER_ANNUAL": "price_starter_annual",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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

    async def fake_rpc(self: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "stripe_customer_id": None}

    monkeypatch.setattr("src.clients.supabase.SupabaseClient.rpc", fake_rpc)


def _install_fake_stripe(monkeypatch: pytest.MonkeyPatch, calls: dict[str, Any]) -> None:
    stripe_mod = types.ModuleType("stripe")
    stripe_mod.api_key = ""

    class FakeSessions:
        @staticmethod
        def create(params: dict[str, Any]) -> Any:
            calls["checkout"] = params
            return types.SimpleNamespace(url="https://checkout.stripe.test/session")

    class FakePortalSessions:
        @staticmethod
        def create(params: dict[str, Any]) -> Any:
            calls["portal"] = params
            return types.SimpleNamespace(url="https://billing.stripe.test/portal")

    class FakeSubscriptions:
        @staticmethod
        def retrieve(sub_id: str) -> dict[str, Any]:
            calls["subscription_retrieve"] = sub_id
            return calls.get(
                "subscription_object",
                {
                    "id": sub_id,
                    "status": "active",
                    "customer": "cus_123",
                    "created": 1700000000,
                    "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
                },
            )

    class FakeStripeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.checkout = types.SimpleNamespace(sessions=FakeSessions)
            self.billing_portal = types.SimpleNamespace(sessions=FakePortalSessions)
            self.subscriptions = FakeSubscriptions()

    stripe_mod.StripeClient = FakeStripeClient

    def construct_event(payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        calls["webhook"] = {"payload": payload, "signature": signature, "secret": secret}
        if signature != "valid-signature":
            raise ValueError("bad signature")
        return calls["event"]

    stripe_mod.Webhook = types.SimpleNamespace(construct_event=construct_event)
    monkeypatch.setitem(sys.modules, "stripe", stripe_mod)


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


def test_webhook_completed_binds_subscription_without_grant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {
        "event": {
            "id": "evt_checkout123",
            "created": 1700000000,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_123",
                    "payment_status": "paid",
                    "mode": "subscription",
                    "metadata": {
                        "plan": "growth",
                        "user_id": "11111111-1111-1111-1111-111111111111",
                    },
                    "client_reference_id": "11111111-1111-1111-1111-111111111111",
                    "customer": "cus_123",
                    "subscription": "sub_123",
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
            "muse_apply_billing_event",
            {
                "p_event": {
                    "event_id": "evt_checkout123",
                    "created": 1700000000,
                    "kind": "checkout.session.completed",
                    "object_id": "cs_123",
                    "customer": "cus_123",
                    "action": "checkout",
                    "user_id": "11111111-1111-1111-1111-111111111111",
                    "plan": "growth",
                    "subscription": "sub_123",
                }
            },
        )
    ]


def test_webhook_invoice_paid_grants_subscription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {
        "event": {
            "id": "evt_inv123",
            "created": 1700000010,
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_123",
                    "status": "paid",
                    "paid": True,
                    "billing_reason": "subscription_cycle",
                    "subscription": "sub_123",
                    "customer": "cus_123",
                    "lines": {
                        "has_more": False,
                        "data": [
                            {
                                "price": {"id": "price_growth"},
                                "subscription": "sub_123",
                                "quantity": 1,
                                "period": {"start": 1700000000, "end": 1702592000},
                            }
                        ],
                    },
                }
            },
        },
        "subscription_object": {
            "id": "sub_123",
            "status": "active",
            "customer": "cus_123",
            "created": 1700000000,
            "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
        },
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
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
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
            "muse_apply_billing_event",
            {
                "p_event": {
                    "event_id": "evt_inv123",
                    "created": 1700000010,
                    "kind": "invoice.paid",
                    "object_id": "in_123",
                    "customer": "cus_123",
                    "action": "paid",
                    "subscription": "sub_123",
                    "user_id": "11111111-1111-1111-1111-111111111111",
                    "plan": "growth",
                    "period_start": 1700000000,
                    "period_end": 1702592000,
                    "subscription_created": 1700000000,
                    "status": "active",
                }
            },
        )
    ]


def test_webhook_subscription_deleted_updates_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {
        "event": {
            "id": "evt_subdel123",
            "created": 1700000050,
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_123",
                    "created": 1700000000,
                    "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
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
            "muse_apply_billing_event",
            {
                "p_event": {
                    "event_id": "evt_subdel123",
                    "created": 1700000050,
                    "kind": "customer.subscription.deleted",
                    "object_id": "sub_123",
                    "customer": "cus_123",
                    "action": "state",
                    "subscription": "sub_123",
                    "user_id": "11111111-1111-1111-1111-111111111111",
                    "status": "canceled",
                    "subscription_created": 1700000000,
                }
            },
        )
    ]


def test_webhook_unpaid_checkout_ignored(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {
        "event": {
            "id": "evt_unpaid123",
            "created": 1700000000,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_unpaid",
                    "payment_status": "unpaid",
                    "mode": "subscription",
                    "metadata": {
                        "plan": "growth",
                        "user_id": "11111111-1111-1111-1111-111111111111",
                    },
                    "client_reference_id": "11111111-1111-1111-1111-111111111111",
                    "customer": "cus_123",
                    "subscription": "sub_123",
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
    assert rpc_calls == []


@pytest.fixture
def billing_harness(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"rpc_calls": []}
    _install_fake_stripe(monkeypatch, calls)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    monkeypatch.setenv("STRIPE_PRICE_UNLIMITED", "price_unlimited")

    async def fake_rpc(self: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
        calls["rpc_calls"].append((name, params))
        if calls.get("error"):
            raise RuntimeError("private upstream response")
        return calls.get("result", {"allowed": True})

    monkeypatch.setattr("src.clients.supabase.SupabaseClient.rpc", fake_rpc)
    return calls


def _modern_invoice() -> dict[str, Any]:
    return {
        "id": "evt_modern",
        "created": 1700000000,
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_modern",
                "status": "paid",
                "customer": "cus_123",
                "billing_reason": "subscription_cycle",
                "parent": {"subscription_details": {"subscription": "sub_123"}},
                "lines": {
                    "has_more": False,
                    "data": [
                        {
                            "quantity": 1,
                            "parent": {
                                "subscription_item_details": {
                                    "subscription": "sub_123",
                                    "proration": False,
                                }
                            },
                            "pricing": {"price_details": {"price": "price_growth"}},
                            "period": {"start": 1700000000, "end": 1702592000},
                        }
                    ],
                },
            }
        },
    }


def _post_event(client: TestClient) -> Any:
    return client.post(
        "/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "valid-signature"}
    )


def test_current_invoice_without_removed_paid_field(
    client: TestClient, billing_harness: dict[str, Any]
) -> None:
    billing_harness["event"] = _modern_invoice()
    response = _post_event(client)
    assert response.status_code == 200, response.text
    data = billing_harness["rpc_calls"][0][1]["p_event"]
    assert data["action"] == "paid"
    assert data["status"] == "active"
    assert data["subscription"] == "sub_123"


@pytest.mark.parametrize(
    "defect",
    [
        "open",
        "legacy_false",
        "wrong_customer",
        "wrong_subscription",
        "other_line",
        "quantity",
        "proration",
        "paginated",
        "unpriced",
        "bad_period",
        "boolean_period",
    ],
)
def test_invalid_invoice_cannot_grant(
    client: TestClient, billing_harness: dict[str, Any], defect: str
) -> None:
    event = _modern_invoice()
    obj = event["data"]["object"]
    line = obj["lines"]["data"][0]
    if defect == "open":
        obj["status"] = "open"
    elif defect == "legacy_false":
        obj["paid"] = False
    elif defect in {"wrong_customer", "wrong_subscription"}:
        billing_harness["subscription_object"] = {
            "id": "sub_wrong" if defect == "wrong_subscription" else "sub_123",
            "customer": "cus_wrong" if defect == "wrong_customer" else "cus_123",
        }
    elif defect == "other_line":
        line["parent"]["subscription_item_details"]["subscription"] = "sub_other"
    elif defect == "quantity":
        line["quantity"] = 2
    elif defect == "proration":
        line["parent"]["subscription_item_details"]["proration"] = True
    elif defect == "paginated":
        obj["lines"]["has_more"] = True
    elif defect == "unpriced":
        line["pricing"]["price_details"]["price"] = "price_unknown"
    elif defect == "bad_period":
        line["period"]["end"] = line["period"]["start"]
    else:
        line["period"]["start"] = True
    billing_harness["event"] = event
    response = _post_event(client)
    assert response.status_code == (200 if defect in {"open", "legacy_false"} else 503)
    assert billing_harness["rpc_calls"] == []


@pytest.mark.parametrize("failure", ["exception", "rejected", "empty"])
def test_webhook_failure_is_retryable_and_sanitized(
    client: TestClient, billing_harness: dict[str, Any], failure: str
) -> None:
    billing_harness["event"] = _modern_invoice()
    if failure == "exception":
        billing_harness["error"] = True
    else:
        billing_harness["result"] = {"allowed": False} if failure == "rejected" else {}
    response = _post_event(client)
    assert response.status_code == 503
    assert "private upstream" not in response.text
    billing_harness.pop("error", None)
    billing_harness["result"] = {"allowed": True}
    assert _post_event(client).status_code == 200
    assert len(billing_harness["rpc_calls"]) == 2


@pytest.mark.parametrize(
    "kind", ["checkout.session.completed", "checkout.session.async_payment_succeeded"]
)
@pytest.mark.parametrize("paid", ["paid", "unpaid", "no_payment_required"])
def test_starter_checkout_requires_paid_status(
    client: TestClient, billing_harness: dict[str, Any], kind: str, paid: str
) -> None:
    owner = "11111111-1111-1111-1111-111111111111"
    billing_harness["event"] = {
        "id": "evt_starter",
        "created": 1700000000,
        "type": kind,
        "data": {
            "object": {
                "id": "cs_starter",
                "customer": "cus_123",
                "mode": "subscription",
                "subscription": "sub_starter",
                "payment_status": paid,
                "metadata": {"plan": "starter", "user_id": owner},
                "client_reference_id": owner,
            }
        },
    }
    assert _post_event(client).status_code == 200
    assert len(billing_harness["rpc_calls"]) == (1 if paid == "paid" else 0)
    if paid == "paid":
        sent = billing_harness["rpc_calls"][0][1]["p_event"]
        assert (sent["action"], sent["plan"], sent["subscription"]) == (
            "checkout",
            "starter",
            "sub_starter",
        )


def test_legacy_one_time_starter_checkout_is_rejected(
    client: TestClient, billing_harness: dict[str, Any]
) -> None:
    owner = "11111111-1111-1111-1111-111111111111"
    billing_harness["event"] = {
        "id": "evt_pack",
        "created": 1700000000,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_pack",
                "customer": "cus_123",
                "mode": "payment",
                "payment_status": "paid",
                "metadata": {"plan": "starter", "user_id": owner},
                "client_reference_id": owner,
            }
        },
    }
    assert _post_event(client).status_code == 503
    assert billing_harness["rpc_calls"] == []


@pytest.mark.parametrize("interval", ["month", "year"])
def test_starter_invoice_grants_starter_for_either_price(
    client: TestClient,
    billing_harness: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    interval: str,
) -> None:
    monkeypatch.setenv("STRIPE_PRICE_STARTER_MONTHLY", "price_starter_m")
    monkeypatch.setenv("STRIPE_PRICE_STARTER_ANNUAL", "price_starter_y")
    from src.config import get_settings

    get_settings.cache_clear()
    event = _modern_invoice()
    line = event["data"]["object"]["lines"]["data"][0]
    line["pricing"]["price_details"]["price"] = (
        "price_starter_m" if interval == "month" else "price_starter_y"
    )
    line["period"]["end"] = line["period"]["start"] + (2592000 if interval == "month" else 31536000)
    billing_harness["event"] = event
    try:
        assert _post_event(client).status_code == 200
    finally:
        get_settings.cache_clear()
    sent = billing_harness["rpc_calls"][0][1]["p_event"]
    assert (sent["action"], sent["plan"]) == ("paid", "starter")
    assert sent["period_end"] - sent["period_start"] == (
        2592000 if interval == "month" else 31536000
    )


def test_subscription_without_metadata_uses_durable_owner(
    client: TestClient, billing_harness: dict[str, Any]
) -> None:
    billing_harness["event"] = {
        "id": "evt_deleted",
        "created": 1700000010,
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_123", "customer": "cus_123", "created": 1700000000}},
    }
    assert _post_event(client).status_code == 200
    assert billing_harness["rpc_calls"][0][1]["p_event"]["user_id"] is None


def test_checkout_reuses_owned_customer_and_copies_subscription_metadata(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _verified_account(monkeypatch)
    calls: dict[str, Any] = {}
    _install_fake_stripe(monkeypatch, calls)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")

    async def usage(self: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"allowed": True, "stripe_customer_id": "cus_owned"}

    monkeypatch.setattr("src.clients.supabase.SupabaseClient.rpc", usage)
    response = client.post("/api/v1/billing/checkout", json={"plan": "growth"})
    assert response.status_code == 200
    assert calls["checkout"]["customer"] == "cus_owned"
    assert "customer_email" not in calls["checkout"]
    assert calls["checkout"]["subscription_data"]["metadata"] == calls["checkout"]["metadata"]


def test_real_stripe_signature_and_expanded_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import hmac
    import json
    import time

    import stripe

    from src.api.billing import _id

    assert _id(stripe.StripeObject.construct_from({"id": "cus_expanded"}, None)) == "cus_expanded"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
    monkeypatch.setattr("src.api.billing._stripe", lambda: None)
    payload = json.dumps({"type": "unhandled.event"}).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        b"whsec_placeholder", str(timestamp).encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={"stripe-signature": f"t={timestamp},v1={signature}"},
        )
        assert response.status_code == 200
        response = client.post(
            "/api/v1/billing/webhook",
            content=payload + b" ",
            headers={"stripe-signature": f"t={timestamp},v1={signature}"},
        )
        assert response.status_code == 400


def test_real_sdk_signed_invoice_grants_through_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real Stripe Event/Subscription objects (not dicts) must normalize, not 503."""
    import hashlib
    import hmac
    import json
    import time

    import stripe

    from src.config import get_settings

    rpc_calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_rpc(self: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
        rpc_calls.append((name, params))
        return {"allowed": True}

    subscription = stripe.Subscription.construct_from(
        {
            "id": "sub_123",
            "object": "subscription",
            "status": "active",
            "customer": {"id": "cus_123", "object": "customer"},
            "created": 1700000000,
            "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
        },
        None,
    )
    fake_client = types.SimpleNamespace(
        subscriptions=types.SimpleNamespace(retrieve=lambda sub_id: subscription)
    )
    monkeypatch.setattr("src.api.billing._stripe", lambda: fake_client)
    monkeypatch.setattr("src.clients.supabase.SupabaseClient.rpc", fake_rpc)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    payload = json.dumps(_modern_invoice()).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        b"whsec_placeholder", str(timestamp).encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/billing/webhook",
                content=payload,
                headers={"stripe-signature": f"t={timestamp},v1={signature}"},
            )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 200, response.text
    assert len(rpc_calls) == 1
    event = rpc_calls[0][1]["p_event"]
    assert event["action"] == "paid"
    assert event["customer"] == "cus_123"
    assert event["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert (event["plan"], event["status"]) == ("growth", "active")


def test_billing_sql_regressions_on_local_postgres() -> None:
    """Runs the real schema + migration on local PostgreSQL WASM when PGlite is installed."""
    import os
    import shutil
    import subprocess
    from pathlib import Path

    pglite = os.environ.get("BILLING_PGLITE_DIR", "")
    node = shutil.which("node")
    if not node or not pglite or not Path(pglite, "dist/index.js").is_file():
        pytest.skip("Set BILLING_PGLITE_DIR to a local @electric-sql/pglite install to run")
    root = Path(__file__).resolve().parents[1]
    for script, marker in (
        ("tests/billing_sql_regression.mjs", "SQL regressions passed"),
        ("tests/billing_sql_rollback.mjs", "ROLLBACK OK"),
    ):
        result = subprocess.run(
            [node, str(root / script)], capture_output=True, text=True, timeout=120, check=False
        )
        assert result.returncode == 0, f"{script}\n{result.stdout}\n{result.stderr[-4000:]}"
        assert marker in result.stdout


@pytest.mark.parametrize(
    ("current", "requested", "expected"),
    [
        ("growth", "unlimited", 409),
        ("growth", "growth", 409),
        ("unlimited", "growth", 409),
        ("growth", "starter", 409),
        ("starter", "starter", 409),
        ("starter", "growth", 409),
        ("trial", "starter", 200),
        ("trial", "unlimited", 200),
    ],
)
def test_checkout_never_starts_a_second_subscription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, current: str, requested: str, expected: int
) -> None:
    _verified_account(monkeypatch)
    calls: dict[str, Any] = {}
    _install_fake_stripe(monkeypatch, calls)
    for name, value in {
        "STRIPE_SECRET_KEY": "sk_test_placeholder",
        "STRIPE_PRICE_STARTER_MONTHLY": "price_starter",
        "STRIPE_PRICE_GROWTH": "price_growth",
        "STRIPE_PRICE_UNLIMITED": "price_unlimited",
    }.items():
        monkeypatch.setenv(name, value)

    async def usage(self: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
        subscribed = current != "trial"
        return {
            "allowed": True,
            "plan": current,
            "stripe_customer_id": "cus_owned",
            "resets_at": "2026-12-09T00:00:00+00:00" if subscribed else None,
        }

    monkeypatch.setattr("src.clients.supabase.SupabaseClient.rpc", usage)
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/billing/checkout", json={"plan": requested})
    finally:
        get_settings.cache_clear()
    assert response.status_code == expected, response.text
    assert ("checkout" in calls) == (expected == 200)
    if expected == 409:
        assert "no second subscription" in response.json()["detail"]


def test_unpriced_plan_reports_pricing_not_generic_outage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _verified_account(monkeypatch)
    _install_fake_stripe(monkeypatch, {})
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.delenv("STRIPE_PRICE_UNLIMITED", raising=False)
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/billing/checkout", json={"plan": "unlimited"})
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert "not priced yet" in response.json()["detail"]


@pytest.mark.parametrize(
    ("plan", "interval", "expected", "price"),
    [
        ("starter", "month", 200, "price_starter_m"),
        ("starter", "year", 200, "price_starter_y"),
        ("growth", "year", 422, None),
    ],
)
def test_checkout_uses_the_chosen_billing_interval(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    plan: str,
    interval: str,
    expected: int,
    price: str | None,
) -> None:
    _verified_account(monkeypatch)
    calls: dict[str, Any] = {}
    _install_fake_stripe(monkeypatch, calls)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_PRICE_STARTER_MONTHLY", "price_starter_m")
    monkeypatch.setenv("STRIPE_PRICE_STARTER_ANNUAL", "price_starter_y")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/billing/checkout", json={"plan": plan, "interval": interval}
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == expected, response.text
    if price:
        assert calls["checkout"]["mode"] == "subscription"
        assert calls["checkout"]["line_items"] == [{"price": price, "quantity": 1}]
        assert calls["checkout"]["subscription_data"]["metadata"]["plan"] == "starter"


@pytest.mark.parametrize(
    ("env", "explicit", "expected"),
    [
        ("preview", None, "https://muse-abc123.vercel.app"),
        ("preview", "https://pinned.example", "https://pinned.example"),
        ("production", None, "https://meta-smb-gtm.vercel.app"),
    ],
)
def test_checkout_redirects_return_to_the_deployment_that_started_them(
    monkeypatch: pytest.MonkeyPatch, env: str, explicit: str | None, expected: str
) -> None:
    from src.config import get_settings

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", env)
    monkeypatch.setenv("VERCEL_URL", "muse-abc123.vercel.app")
    if explicit:
        monkeypatch.setenv("APP_URL", explicit)
    else:
        monkeypatch.delenv("APP_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().app_url == expected
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "missing",
    [
        None,
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_STARTER_MONTHLY",
        "STRIPE_PRICE_STARTER_ANNUAL",
    ],
)
def test_billing_status_and_checkout_follow_full_configuration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, missing: str | None
) -> None:
    from src.config import get_settings

    if missing:
        monkeypatch.setenv(missing, "")
    get_settings.cache_clear()
    status = client.get("/api/v1/billing/status")
    assert status.status_code == 200
    assert status.json()["available"] is (missing is None)
    assert "sk_test" not in status.text and "price_" not in status.text
    checkout = client.post("/api/v1/billing/checkout", json={"plan": "starter"})
    # Unconfigured billing answers before asking anyone to sign in.
    assert checkout.status_code == (401 if missing is None else 503)
