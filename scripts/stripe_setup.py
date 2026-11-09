"""Create (or find) the Muse Stripe catalog and webhook. Safe to rerun; never prints secrets.

Prices are addressed by stable lookup keys, so the same command builds an identical catalog in
test mode now and in live mode later:

    python scripts/stripe_setup.py                                   # catalog only
    python scripts/stripe_setup.py --env preview --webhook-url URL   # + that env's webhook
    python scripts/stripe_setup.py --env preview --push-vercel       # + copy settings to Vercel

Going live: put the live secret key in .env as STRIPE_SECRET_KEY, then run
    python scripts/stripe_setup.py --live --env production \
        --webhook-url https://meta-smb-gtm.vercel.app/api/v1/billing/webhook --push-vercel
and redeploy production.

Reads STRIPE_SECRET_KEY from the environment or .env and refuses a live key unless --live is
passed. Each environment has one webhook endpoint (tagged in Stripe metadata); a new URL updates
it in place, so its signing secret survives preview redeploys. A new endpoint's signing secret
(shown by Stripe only once) is saved to .env as STRIPE_WEBHOOK_SECRET_<ENV>. Nothing secret is
printed; --push-vercel pipes values to `vercel env add --sensitive` over stdin.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import stripe
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
PRODUCT = {"name": "Muse Starter", "metadata": {"muse_plan": "starter"}}
PRICES = {
    # lookup_key: (unit amount in cents, interval, env var the app reads)
    "muse_starter_monthly": (1200, "month", "STRIPE_PRICE_STARTER_MONTHLY"),
    "muse_starter_annual": (10800, "year", "STRIPE_PRICE_STARTER_ANNUAL"),
}
# Must match the event kinds src/api/billing.py handles.
WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
]


def _secret_key(allow_live: bool) -> str:
    key = os.environ.get("STRIPE_SECRET_KEY") or dotenv_values(ENV_FILE).get("STRIPE_SECRET_KEY")
    if not key:
        sys.exit("STRIPE_SECRET_KEY is not set (environment or .env).")
    if key.startswith(("sk_live_", "rk_live_")) and not allow_live:
        sys.exit("Refusing a live key without --live.")
    if not key.startswith(("sk_test_", "rk_test_", "sk_live_", "rk_live_")):
        sys.exit("STRIPE_SECRET_KEY does not look like a Stripe secret key.")
    return key


def _store_env(name: str, value: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)


def ensure_catalog(client: stripe.StripeClient) -> dict[str, str]:
    found = {
        p.lookup_key: p
        for p in client.v1.prices.list({"lookup_keys": list(PRICES), "limit": 10}).data
    }
    product_id = next((p.product for p in found.values()), None)
    if product_id is None:
        product_id = client.v1.products.create(PRODUCT).id
    ids = {}
    for lookup_key, (amount, interval, env_name) in PRICES.items():
        price = found.get(lookup_key)
        if price is None or price.unit_amount != amount or price.recurring.interval != interval:
            # transfer_lookup_key moves the key to the new price if an old one held it.
            price = client.v1.prices.create(
                {
                    "product": product_id,
                    "currency": "usd",
                    "unit_amount": amount,
                    "recurring": {"interval": interval},
                    "lookup_key": lookup_key,
                    "transfer_lookup_key": True,
                    "metadata": {"muse_plan": "starter"},
                }
            )
        ids[env_name] = price.id
    return ids


def _redact(url: str) -> str:
    return url.split("?", 1)[0] + ("?…" if "?" in url else "")


def ensure_webhook(client: stripe.StripeClient, env: str, url: str) -> str:
    for endpoint in client.v1.webhook_endpoints.list({"limit": 100}).data:
        if endpoint.to_dict().get("metadata", {}).get("muse_env") == env:
            client.v1.webhook_endpoints.update(
                endpoint.id, {"url": url, "enabled_events": WEBHOOK_EVENTS, "disabled": False}
            )
            return f"{endpoint.id} → {_redact(url)} (updated; signing secret unchanged)"
    endpoint = client.v1.webhook_endpoints.create(
        {
            "url": url,
            "enabled_events": WEBHOOK_EVENTS,
            "description": f"Muse Growth Studio billing ({env})",
            "metadata": {"muse_env": env},
        }
    )
    _store_env(f"STRIPE_WEBHOOK_SECRET_{env.upper()}", endpoint.secret)
    return f"{endpoint.id} → {_redact(url)} (new; signing secret saved to .env)"


def push_vercel(env: str, key: str, prices: dict[str, str]) -> None:
    webhook_secret = dotenv_values(ENV_FILE).get(f"STRIPE_WEBHOOK_SECRET_{env.upper()}")
    values = {"STRIPE_SECRET_KEY": key, **prices}
    if webhook_secret:
        values["STRIPE_WEBHOOK_SECRET"] = webhook_secret
    else:
        print(f"note: no STRIPE_WEBHOOK_SECRET_{env.upper()} in .env; webhook secret not pushed")
    for name, value in values.items():
        subprocess.run(
            ["vercel", "env", "rm", name, env, "--yes"], cwd=ROOT, capture_output=True, check=False
        )
        added = subprocess.run(
            ["vercel", "env", "add", name, env, "--sensitive"],
            cwd=ROOT,
            input=value,
            text=True,
            capture_output=True,
            check=False,
        )
        print(f"vercel {env}: {name} {'set' if added.returncode == 0 else 'FAILED'}")
        if added.returncode != 0:
            sys.exit(f"vercel env add {name} failed: {added.stderr.strip()[-300:]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", choices=["preview", "production"], help="Target environment")
    parser.add_argument("--webhook-url", help="Public URL of /api/v1/billing/webhook")
    parser.add_argument("--push-vercel", action="store_true", help="Copy settings to Vercel --env")
    parser.add_argument("--live", action="store_true", help="Allow a live-mode key")
    args = parser.parse_args()
    if (args.webhook_url or args.push_vercel) and not args.env:
        parser.error("--webhook-url and --push-vercel need --env")
    key = _secret_key(args.live)
    if args.env == "preview" and "_live_" in key:
        sys.exit("Refusing to put a live key on preview deployments.")
    client = stripe.StripeClient(key)
    mode = "LIVE" if "_live_" in key else "test"
    prices = ensure_catalog(client)
    for name, price_id in prices.items():
        _store_env(name, price_id)
        print(f"{name}={price_id}")
    if args.webhook_url:
        print("webhook:", ensure_webhook(client, args.env, args.webhook_url))
    if args.push_vercel:
        push_vercel(args.env, key, prices)
    print(f"Done ({mode} mode).")


if __name__ == "__main__":
    main()
