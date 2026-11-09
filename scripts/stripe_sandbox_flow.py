"""End-to-end billing check against the Stripe SANDBOX. Test mode only; never prints secrets.

What it does (no app account or browser needed):
1. Pauses this environment's Stripe webhook so synthetic customers don't hit the deployment.
2. Validates the exact Checkout Session parameters the app sends (monthly and annual).
3. Creates real test-mode subscriptions paid with Stripe test payment methods: monthly, annual,
   a declined card, and a cancellation.
4. Downloads the real signed-event payloads Stripe generated and runs each through the app's own
   webhook normalizer (`src.api.billing._billing_event`, real Stripe SDK objects).
5. Replays the normalized events into the real Supabase schema + billing migration on local
   PostgreSQL WASM (tests/billing_sql_replay.mjs) and checks the resulting plans and run limits.
6. Cancels/deletes the synthetic Stripe objects and restores the webhook.

    BILLING_PGLITE_DIR=/tmp/muse-billing-sql/node_modules/@electric-sql/pglite \\
        .venv/bin/python scripts/stripe_sandbox_flow.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import stripe  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

HANDLED = [
    "checkout.session.completed",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
]


def _client() -> stripe.StripeClient:
    key = dotenv_values(ROOT / ".env").get("STRIPE_SECRET_KEY", "")
    if not key.startswith(("sk_test_", "rk_test_")):
        sys.exit("This check only runs with a Stripe TEST key in .env.")
    env = dotenv_values(ROOT / ".env")
    for name in ("STRIPE_PRICE_STARTER_MONTHLY", "STRIPE_PRICE_STARTER_ANNUAL"):
        os.environ[name] = env.get(name, "")
    os.environ["STRIPE_SECRET_KEY"] = key
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_unused_by_this_check")
    return stripe.StripeClient(key)


def _set_webhooks(client: stripe.StripeClient, disabled: bool, only: set[str] | None) -> set[str]:
    changed = set()
    for endpoint in client.v1.webhook_endpoints.list({"limit": 100}).data:
        if only is not None and endpoint.id not in only:
            continue
        if (endpoint.status == "disabled") != disabled:
            client.v1.webhook_endpoints.update(endpoint.id, {"disabled": disabled})
            changed.add(endpoint.id)
    return changed


def _subscribe(
    client: stripe.StripeClient, price: str, pm: str, user: str, tag: str
) -> tuple[str, str]:
    customer = client.v1.customers.create(
        {"description": f"Muse sandbox flow {tag}", "metadata": {"muse_sandbox_flow": tag}}
    )
    # Test tokens like pm_card_visa become a new PaymentMethod when attached.
    pm = client.v1.payment_methods.attach(pm, {"customer": customer.id}).id
    params = {
        "customer": customer.id,
        "items": [{"price": price, "quantity": 1}],
        "default_payment_method": pm,
        "metadata": {"user_id": user, "plan": "starter"},
    }
    if tag == "declined":
        params["payment_behavior"] = "allow_incomplete"
    sub = client.v1.subscriptions.create(params)
    return customer.id, sub.id


async def _normalize(client: stripe.StripeClient, customers: set[str], since: int) -> list[Any]:
    from src.api.billing import _billing_event, _plain
    from src.config import get_settings

    get_settings.cache_clear()
    events: list[Any] = []
    for _ in range(10):  # events are eventually consistent; wait until each customer has some
        events = [
            e
            for e in client.v1.events.list(
                {"created": {"gte": since}, "types": HANDLED, "limit": 100}
            ).data
            if _plain(e)["data"]["object"].get("customer") in customers
        ]
        if {_plain(e)["data"]["object"]["customer"] for e in events} >= customers:
            break
        await asyncio.sleep(2)
    normalized = []
    for event in sorted(events, key=lambda e: (e.created, e.id)):
        data = await _billing_event(_plain(event), client.v1)
        if data is not None:
            normalized.append(data)
    return normalized


def main() -> None:
    client = _client()
    env = dotenv_values(ROOT / ".env")
    monthly, annual = env["STRIPE_PRICE_STARTER_MONTHLY"], env["STRIPE_PRICE_STARTER_ANNUAL"]
    users = {tag: str(uuid.uuid4()) for tag in ("monthly", "annual", "declined", "canceled")}
    since = int(time.time()) - 5
    paused = _set_webhooks(client, disabled=True, only=None)
    customers: dict[str, str] = {}
    subs: dict[str, str] = {}
    try:
        for interval, price in (("month", monthly), ("year", annual)):
            session = client.v1.checkout.sessions.create(
                {
                    "mode": "subscription",
                    "line_items": [{"price": price, "quantity": 1}],
                    "client_reference_id": users["monthly"],
                    "customer_email": "sandbox-flow@example.com",
                    "metadata": {"user_id": users["monthly"], "plan": "starter"},
                    "subscription_data": {
                        "metadata": {"user_id": users["monthly"], "plan": "starter"}
                    },
                    "success_url": "https://meta-smb-gtm.vercel.app/account?billing=success",
                    "cancel_url": "https://meta-smb-gtm.vercel.app/account?billing=cancelled",
                }
            )
            ok = session.url and session.url.startswith("https://checkout.stripe.com/")
            print(f"checkout session params accepted ({interval}): {bool(ok)}")
            client.v1.checkout.sessions.expire(session.id)
        plan = {
            "monthly": (monthly, "pm_card_visa"),
            "annual": (annual, "pm_card_visa"),
            "declined": (monthly, "pm_card_chargeCustomerFail"),
            "canceled": (monthly, "pm_card_visa"),
        }
        for tag, (price, pm) in plan.items():
            customers[tag], subs[tag] = _subscribe(client, price, pm, users[tag], tag)
            status = client.v1.subscriptions.retrieve(subs[tag]).status
            print(f"subscription {tag}: Stripe status {status}")
        client.v1.subscriptions.cancel(subs["canceled"])
        normalized = asyncio.run(_normalize(client, set(customers.values()), since))
        kinds = sorted({(d["kind"], d["action"]) for d in normalized})
        print(f"normalized {len(normalized)} real events: {kinds}")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"users": users, "events": normalized}, handle)
        replay = subprocess.run(
            ["node", str(ROOT / "tests/billing_sql_replay.mjs"), handle.name],
            capture_output=True,
            text=True,
            check=False,
        )
        os.unlink(handle.name)
        print(replay.stdout.strip())
        if replay.returncode != 0:
            sys.exit(f"SQL replay failed:\n{replay.stderr[-3000:]}")
    finally:
        for sub in subs.values():
            try:
                if client.v1.subscriptions.retrieve(sub).status not in {
                    "canceled",
                    "incomplete_expired",
                }:
                    client.v1.subscriptions.cancel(sub)
            except stripe.StripeError:
                pass
        for customer in customers.values():
            with contextlib.suppress(stripe.StripeError):
                client.v1.customers.delete(customer)
        _set_webhooks(client, disabled=False, only=paused)
        print(f"cleanup: synthetic customers deleted; {len(paused)} webhook(s) re-enabled")


if __name__ == "__main__":
    main()
