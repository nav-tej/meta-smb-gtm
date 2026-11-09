"""Stripe Checkout billing for paid run plans.

Every plan is a subscription (1 run = 1 live action). Starter is 20 runs a month, billed
monthly or annually (annual subscribers still get a fresh 20 each month). Growth (50/month) and
Unlimited stay in the code but are not sold until they have Stripe prices. Only verified paid
invoices grant runs (via the webhook); checkout and portal links never grant anything.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from src.clients.supabase import get_supabase_client
from src.config import get_settings
from src.services.accounts import resolve_account

router = APIRouter(prefix="/billing", tags=["billing"])

_PLANS = {
    "starter": {"mode": "subscription", "runs": "20 runs a month"},
    "growth": {"mode": "subscription", "runs": "50 runs a month"},
    "unlimited": {"mode": "subscription", "runs": "Unlimited runs"},
}
# Settings field holding each sellable price. Only Starter has an annual option.
_PRICE_SETTINGS = {
    ("starter", "month"): "stripe_price_starter_monthly",
    ("starter", "year"): "stripe_price_starter_annual",
    ("growth", "month"): "stripe_price_growth",
    ("unlimited", "month"): "stripe_price_unlimited",
}


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern="^(starter|growth|unlimited)$")
    interval: Literal["month", "year"] = "month"


def _stripe() -> Any:
    try:
        import stripe
    except ImportError as err:
        raise HTTPException(503, "Billing is not installed on this server.") from err
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Billing is not configured yet.")
    client = stripe.StripeClient(settings.stripe_secret_key)
    return getattr(client, "v1", client)


def _price_id(plan: str, interval: str = "month") -> str:
    field = _PRICE_SETTINGS.get((plan, interval))
    if field is None:
        raise HTTPException(422, f"The {plan.title()} plan has no {interval}ly billing option.")
    price = getattr(get_settings(), field, "")
    if not price:
        raise HTTPException(503, f"The {plan.title()} plan is not priced yet.")
    return price


def _plan_for_price(price: str | None) -> str | None:
    """Map a paid invoice line's price back to the plan it grants."""
    if not price:
        return None
    settings = get_settings()
    for (plan, _interval), field in _PRICE_SETTINGS.items():
        if getattr(settings, field, "") == price:
            return plan
    return None


def billing_available() -> bool:
    """Checkout is offered only when payments can be both taken and recorded."""
    settings = get_settings()
    return all(
        (
            settings.stripe_secret_key,
            settings.stripe_webhook_secret,
            settings.stripe_price_starter_monthly,
            settings.stripe_price_starter_annual,
        )
    )


@router.get("/status")
async def status(response: Response) -> dict[str, Any]:
    """Tell the pricing dialog whether to offer checkout; reveals no configuration values."""
    response.headers["Cache-Control"] = "no-store"
    available = billing_available()
    return {"available": available, "intervals": ["month", "year"] if available else []}


@router.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request, response: Response) -> dict[str, str]:
    """Create a Checkout Session for a verified account; grants nothing yet."""
    if not billing_available():
        raise HTTPException(503, "Paid plans aren't available yet.")
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    stripe = _stripe()
    app_url = get_settings().app_url.rstrip("/")
    try:
        usage = await get_supabase_client().rpc("muse_usage_status", {"p_user_id": account.user_id})
        if usage.get("allowed") is not True:
            raise ValueError("Billing account lookup failed")
        current = usage.get("plan")
        # resets_at is only set while a paid subscription period is active.
        if usage.get("resets_at") or current in {"growth", "unlimited"}:
            # A second Checkout would start a second, separately charged subscription.
            raise HTTPException(
                409,
                f"You already have the {str(current).title()} plan, so no second subscription "
                "was started. Plan changes aren't available in the app yet.",
            )
        metadata = {"user_id": account.user_id, "plan": body.plan}
        params = dict(
            mode=_PLANS[body.plan]["mode"],
            line_items=[{"price": _price_id(body.plan, body.interval), "quantity": 1}],
            client_reference_id=account.user_id,
            customer_email=account.email,
            metadata=metadata,
            success_url=app_url + "/account?billing=success",
            cancel_url=app_url + "/account?billing=cancelled",
        )
        if usage.get("stripe_customer_id"):
            params.pop("customer_email")
            params["customer"] = usage["stripe_customer_id"]
        params["subscription_data"] = {"metadata": metadata}
        session = await run_in_threadpool(stripe.checkout.sessions.create, params)
    except HTTPException:
        raise
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
        session = await run_in_threadpool(
            stripe.billing_portal.sessions.create,
            {"customer": customer, "return_url": get_settings().app_url.rstrip("/") + "/account"},
        )
    except Exception as err:
        raise HTTPException(503, "Billing portal is unavailable. Try again shortly.") from err
    return {"url": session.url}


def _plain(value: Any) -> Any:
    """Stripe SDK v13+ objects are not dicts (no .get()); convert them once at the boundary."""
    to_dict = getattr(value, "to_dict", None)
    return to_dict() if callable(to_dict) else value


def _id(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return _plain(value).get("id")


def _owner(obj: Any) -> str | None:
    value = (obj.get("metadata") or {}).get("user_id")
    if value:
        return str(UUID(value))
    return None


def _invoice_subscription(obj: Any) -> str | None:
    return _id(obj.get("subscription")) or _id(
        ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
    )


async def _billing_event(event: Any, stripe: Any) -> dict[str, Any] | None:
    """Normalize signed events. Only paid invoices grant recurring access."""
    kind = event["type"]
    if kind not in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "invoice.paid",
        "invoice.payment_failed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        return None
    obj = event["data"]["object"]
    data = {
        "event_id": event["id"],
        "created": event["created"],
        "kind": kind,
        "object_id": obj["id"],
        "customer": _id(obj.get("customer")),
    }
    if kind in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        if obj.get("payment_status") != "paid":
            return None
        plan = (obj.get("metadata") or {}).get("plan")
        if plan not in _PLANS or obj.get("mode") != _PLANS[plan]["mode"]:
            raise ValueError("Invalid checkout plan")
        owner = _owner(obj)
        if not owner or obj.get("client_reference_id") != owner:
            raise ValueError("Invalid checkout owner")
        data.update(
            action="checkout", user_id=owner, plan=plan, subscription=_id(obj.get("subscription"))
        )
        if not data["subscription"]:
            raise ValueError("Missing subscription")
    elif kind in {"invoice.paid", "invoice.payment_failed"}:
        subscription = _invoice_subscription(obj)
        if not subscription:
            return None
        if kind == "invoice.payment_failed":
            data.update(action="failed", subscription=subscription)
            return data
        if obj.get("status") != "paid" or obj.get("paid") is False:
            return None
        # Metadata is only a bootstrap fallback; SQL enforces immutable ownership.
        sub = _plain(await run_in_threadpool(stripe.subscriptions.retrieve, subscription))
        if sub.get("id") != subscription or _id(sub.get("customer")) != data["customer"]:
            raise ValueError("Subscription customer mismatch")
        lines = (obj.get("lines") or {}).get("data", [])
        if (obj.get("lines") or {}).get("has_more"):
            raise ValueError("Unsupported paginated invoice")
        eligible = []
        for line in lines:
            price = _id(line.get("price")) or (
                (line.get("pricing") or {}).get("price_details") or {}
            ).get("price")
            details = (line.get("parent") or {}).get("subscription_item_details") or {}
            line_subscription = _id(line.get("subscription")) or _id(details.get("subscription"))
            if line_subscription != subscription:
                continue
            if line.get("quantity") != 1 or line.get("proration") or details.get("proration"):
                continue
            plan = _plan_for_price(price)
            if plan:
                eligible.append((plan, line.get("period") or {}))
        if len(eligible) != 1 or obj.get("billing_reason") not in {
            "subscription_create",
            "subscription_cycle",
        }:
            raise ValueError("Unsupported subscription invoice")
        plan, period = eligible[0]
        start, end = period.get("start"), period.get("end")
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            raise ValueError("Invalid invoice period")
        data.update(
            action="paid",
            subscription=subscription,
            user_id=_owner(sub),
            plan=plan,
            period_start=start,
            period_end=end,
            subscription_created=sub["created"],
            status=sub["status"],
        )
    elif kind in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        status = obj.get("status")
        if kind == "customer.subscription.deleted":
            status = "canceled"
        elif kind == "customer.subscription.paused":
            status = "paused"
        if status not in {
            "active",
            "trialing",
            "past_due",
            "unpaid",
            "incomplete",
            "incomplete_expired",
            "paused",
            "canceled",
        }:
            raise ValueError("Invalid subscription status")
        data.update(
            action="state",
            subscription=obj["id"],
            user_id=_owner(obj),
            status=status,
            subscription_created=obj["created"],
        )
    else:
        return None
    if not data["customer"]:
        raise ValueError("Missing customer")
    return data


@router.post("/webhook")
async def webhook(request: Request) -> dict[str, bool]:
    """Acknowledge only after the event and entitlement transaction commits."""
    import stripe as stripe_sdk

    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Billing webhooks are not configured yet.")
    payload = await request.body()
    try:
        event = stripe_sdk.Webhook.construct_event(
            payload, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret
        )
    except Exception as err:
        raise HTTPException(400, "Invalid webhook signature.") from err
    try:
        data = await _billing_event(_plain(event), _stripe())
        if data is not None:
            result = await get_supabase_client().rpc("muse_apply_billing_event", {"p_event": data})
            if result.get("allowed") is not True:
                raise ValueError("Billing event rejected")
    except Exception as err:
        # Retry on provider/database failure; never acknowledge a lost entitlement write.
        raise HTTPException(503, "Billing event could not be applied. Retry later.") from err
    if data is not None and not result.get("duplicate"):
        await _report_billing_event(data)
    return {"received": True}


_ANALYTICS_EVENTS = {
    "checkout": "checkout_completed",
    "paid": "subscription_paid",
    "failed": "payment_failed",
}


async def _report_billing_event(data: dict[str, Any]) -> None:
    """Purchase analytics come from verified webhooks, not browser redirects. Best effort."""
    from src.clients import posthog

    user = data.get("user_id")
    event = _ANALYTICS_EVENTS.get(data["action"])
    if data["action"] == "state" and data.get("status") == "canceled":
        event = "subscription_canceled"
    if not user or not event or not posthog.enabled():
        return
    properties: dict[str, Any] = {"plan": data.get("plan"), "stripe_event": data["kind"]}
    if data["action"] == "paid":
        days = (data["period_end"] - data["period_start"]) / 86400
        properties["interval"] = "year" if days > 300 else "month"
    await posthog.capture(event, user, properties)
