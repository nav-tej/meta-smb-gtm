"""Stripe Checkout billing for paid run plans.

Plans (1 run = 1 live action): Starter is a one-time 10-run pack; Growth is
50 runs/month; Unlimited removes the quota. The webhook is the only writer of
entitlements; checkout/portal links never grant runs by themselves.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.clients.supabase import get_supabase_client
from src.config import get_settings
from src.services.accounts import resolve_account

router = APIRouter(prefix="/billing", tags=["billing"])

_PLANS = {
    "starter": {"mode": "payment", "runs": "10 runs, one-time"},
    "growth": {"mode": "subscription", "runs": "50 runs a month"},
    "unlimited": {"mode": "subscription", "runs": "Unlimited runs"},
}


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern="^(starter|growth|unlimited)$")


def _stripe() -> Any:
    try:
        import stripe
    except ImportError as err:
        raise HTTPException(503, "Billing is not installed on this server.") from err
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Billing is not configured yet.")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_id(plan: str) -> str:
    settings = get_settings()
    price = getattr(settings, f"stripe_price_{plan}", "")
    if not price:
        raise HTTPException(503, f"The {plan.title()} plan is not priced yet.")
    return price


@router.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request, response: Response) -> dict[str, str]:
    """Create a Checkout Session for a verified account; grants nothing yet."""
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    stripe = _stripe()
    app_url = get_settings().app_url.rstrip("/")
    try:
        session = stripe.checkout.Session.create(
            mode=_PLANS[body.plan]["mode"],
            line_items=[{"price": _price_id(body.plan), "quantity": 1}],
            client_reference_id=account.user_id,
            customer_email=account.email,
            metadata={"user_id": account.user_id, "plan": body.plan},
            success_url=app_url + "/account?billing=success",
            cancel_url=app_url + "/account?billing=cancelled",
        )
    except Exception as err:
        raise HTTPException(503, "Checkout is unavailable. Try again shortly.") from err
    if not session.url:
        raise HTTPException(503, "Checkout is unavailable. Try again shortly.")
    return {"url": session.url}


@router.post("/portal")
async def portal(request: Request, response: Response) -> dict[str, str]:
    """Open the Stripe customer portal for the verified account's customer."""
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    stripe = _stripe()
    usage = await get_supabase_client().rpc("muse_usage_status", {"p_user_id": account.user_id})
    customer = usage.get("stripe_customer_id")
    if not customer:
        raise HTTPException(409, "No billing account yet. Pick a plan first.")
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer, return_url=get_settings().app_url.rstrip("/") + "/account"
        )
    except Exception as err:
        raise HTTPException(503, "Billing portal is unavailable. Try again shortly.") from err
    return {"url": session.url}


@router.post("/webhook")
async def webhook(request: Request) -> dict[str, bool]:
    """Apply verified Stripe events to entitlements. No auth; signature is auth."""
    stripe = _stripe()
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Billing webhooks are not configured yet.")
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except Exception as err:
        raise HTTPException(400, "Invalid webhook signature.") from err
    kind = event.get("type", "")
    if kind == "checkout.session.completed":
        session = event["data"]["object"]
        plan = (session.get("metadata") or {}).get("plan", "")
        user_id = (session.get("metadata") or {}).get("user_id") or session.get(
            "client_reference_id"
        )
        if plan in _PLANS and user_id:
            await get_supabase_client().rpc(
                "muse_set_plan",
                {
                    "p_user_id": user_id,
                    "p_plan": plan,
                    "p_stripe_customer_id": session.get("customer"),
                },
            )
    elif kind in {"customer.subscription.deleted", "customer.subscription.paused"}:
        subscription = event["data"]["object"]
        customer = subscription.get("customer")
        user_id = (subscription.get("metadata") or {}).get("user_id", "")
        if customer and user_id:
            await get_supabase_client().rpc(
                "muse_set_plan",
                {"p_user_id": user_id, "p_plan": "trial", "p_stripe_customer_id": customer},
            )
    return {"received": True}
