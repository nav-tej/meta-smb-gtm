"""Application settings. The only module that reads environment variables."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    meta_model_api_key: str = ""
    meta_model_api_base_url: str = "https://api.meta.ai/v1"
    muse_spark_model: str = "muse-spark-1.3"
    muse_image_model: str = "muse-image-1.0"
    sam_model: str = "sam-3.1"

    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_api_key: str = ""

    meta_ads_access_token: str = ""
    meta_ad_account_id: str = ""

    crawler_user_agent: str = "MetaSMBGTM/0.1 (+https://github.com/nav-tej/meta-smb-gtm)"
    crawler_max_urls: int = 5000

    output_dir: str = "outputs"

    # Live Muse results are cached on disk so repeat demo runs do not spend API credit.
    result_cache_enabled: bool = True
    result_cache_dir: str = "data/cache"
    result_cache_ttl_seconds: int = 86400

    # Server-side run credits for live Muse calls (see src/services/credits.py). On Vercel the
    # ledger lives in /tmp, so it lasts per function instance; Supabase accounts are durable.
    credits_enabled: bool = True
    credits_dir: str = "data/credits"
    presenter_credits: int = 20
    max_credit_balance: int = 5000

    # Competitor monitor change log and latest snapshots (no Muse call; public crawl only).
    monitor_dir: str = "data/monitor"
    monitor_cooldown_seconds: int = 6 * 3600
    cron_secret: str = ""
    log_level: str = "INFO"

    # Demo mode serves saved live results so a public deployment can't spend Muse credits.
    # Live calls need ?live=true plus an X-Demo-Key header matching DEMO_KEY.
    demo_mode: bool = True
    demo_key: str = ""
    live_calls_per_hour: int = 5
    hosted_environment: bool = False

    # Freemium accounts: verified users spend runs from a Supabase-tracked quota
    # instead of the shared demo key. 1 run = one live action; the trial is 3 runs,
    # one-time (no refill).
    accounts_required: bool = False
    trial_runs: int = 3
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    app_url: str = "https://meta-smb-gtm.vercel.app"
    account_cookie_secure: bool = True

    # Paid tiers via Stripe Checkout. Starter is one-time; Growth/Unlimited are
    # subscriptions. Price IDs come from the Stripe dashboard (test or live).
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Email (Resend): weekly competitor digest and operator alerts. Off without an API key and a
    # token secret. EMAIL_FROM must use a domain verified in Resend.
    resend_api_key: str = ""
    email_from: str = "Muse Growth Studio <digest@nplusalpha.com>"
    email_reply_to: str = "help@nplusalpha.com"
    email_token_secret: str = ""
    email_postal_address: str = ""
    alert_email: str = "help@nplusalpha.com"
    # PostHog product analytics: off unless a project key is set. The key is public by design.
    posthog_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    stripe_price_starter_monthly: str = ""
    stripe_price_starter_annual: str = ""
    stripe_price_growth: str = ""
    stripe_price_unlimited: str = ""


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    load_dotenv(".env.local", override=True)
    fields = Settings.model_fields
    values = {
        name: os.environ[name.upper()].strip()
        for name in fields
        if os.environ.get(name.upper()) and os.environ[name.upper()].strip()
    }
    # Serverless filesystems (Vercel) are read-only except /tmp
    if os.environ.get("VERCEL") and "output_dir" not in values:
        values["output_dir"] = "/tmp/outputs"
    # Serverless filesystems are read-only outside /tmp; the cache then lasts per instance.
    if os.environ.get("VERCEL") and "result_cache_dir" not in values:
        values["result_cache_dir"] = "/tmp/muse-cache"
    if os.environ.get("VERCEL") and "credits_dir" not in values:
        values["credits_dir"] = "/tmp/muse-credits"
    if os.environ.get("VERCEL") and "monitor_dir" not in values:
        values["monitor_dir"] = "/tmp/muse-monitor"
    if os.environ.get("VERCEL"):
        values["hosted_environment"] = True
    # Each preview deployment has its own URL; send Stripe redirects back to it, not production.
    if os.environ.get("VERCEL_ENV") == "preview" and os.environ.get("VERCEL_URL"):
        values.setdefault("app_url", f"https://{os.environ['VERCEL_URL']}")
    return Settings(**values)
