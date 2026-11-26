"""Competitor Intel & Seller Audit routes (Flow 1 + Demo Portal Presets)."""

import base64
import binascii
import hmac
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from src.api.cache_policy import cache_for_everyone, never_cache
from src.api.demo import LiveMode, _client_ip_hash, demo_unavailable
from src.clients.ad_library import (
    MetaAdLibraryClient,
    build_ad_library_search_url,
    load_sample_ad_library_signals,
)
from src.clients.meta import MetaAPIError
from src.clients.supabase import SupabaseError
from src.config import Settings, get_settings
from src.models.intel import (
    CompetitorAdSignalsResponse,
    CompetitorBrief,
    CompetitorIntelRequest,
    SocialCompetitorSignals,
)
from src.models.seller import (
    ScreenshotAnalysis,
    SellerDiagnostics,
    SellerFootprintAudit,
    SellerProfile,
)
from src.services import demo, result_cache, scan_guard, watchlist_store
from src.services.accounts import (
    load_workspace,
    resolve_account,
    save_workspace,
    verify_workspace_owner,
)
from src.services.competitor_checks import (
    MAX_COMPETITORS_PER_CHECK,
    MAX_PAGES_PER_COMPETITOR,
    PER_SITE_CRAWL_TIMEOUT_SECONDS,
    compute_top_insight,
    extract_selected_competitors,
    normalize_competitor_url,
    now_iso_utc,
    run_watchlist_checks,
)
from src.services.competitor_intel import CompetitorIntelService, collect_entries
from src.services.research_cache import NAMESPACE_AD_PREVIEWS, cached_research
from src.services.saved_competitors import (
    ad_library_page_url,
    merge_saved_competitor,
    parse_ad_library_page_id,
)
from src.services.seller_audit import (
    analyze_social_screenshots,
    audit_seller_footprint,
    compute_seller_diagnostics,
)
from src.services.social_extract import extract_social_handles
from src.utils.sitemap import SitemapError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intel"])

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


class AuditSellerRequest(BaseModel):
    profile: SellerProfile
    competitor_brief: CompetitorBrief | None = None
    deterministic_only: bool = False


class IngestStorefrontRequest(BaseModel):
    business_name: str = Field(default="Independent Artist Studio", max_length=160)
    website_url: str = Field(default="", max_length=500)
    marketplace_urls: list[str] = Field(default_factory=list, max_length=10)
    social_urls: list[str] = Field(default_factory=list, max_length=10)
    max_urls_per_source: int = Field(default=30, ge=5, le=100)


class ScreenshotAuditRequest(BaseModel):
    image_base64: str = Field(
        min_length=8,
        description="Base64-encoded PNG/JPEG/WEBP screenshot of IG, FB, Saatchi, Etsy, or shop.",
    )
    context: str = Field(default="Independent fine artist & multi-channel seller", max_length=1000)


def get_competitor_intel_service() -> CompetitorIntelService:
    return CompetitorIntelService()


SOCIAL_LINK_HOSTS = ("facebook.com", "fb.com", "fb.me", "instagram.com")
SOCIAL_LINK_REFUSAL = (
    "That is a Facebook or Instagram link. Muse can't read those pages, so use the "
    "competitor's own website instead. No run was used."
)


def is_social_link(raw_url: str | None) -> bool:
    """True for a Facebook or Instagram address, including a Meta Ad Library search."""
    text = str(raw_url or "").strip()
    if not text:
        return False
    host = (urlparse(text if "://" in text else f"https://{text}").hostname or "").lower()
    return any(host == name or host.endswith(f".{name}") for name in SOCIAL_LINK_HOSTS)


class SaveCompetitorRequest(BaseModel):
    competitor_url: str = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=140)
    brief: CompetitorBrief | None = None
    # Their page in Meta's Ad Library (a view_all_page_id link or the Page ID); "" unlinks.
    ad_library_url: str | None = Field(default=None, max_length=1000)


@router.put("/competitors/saved")
async def save_competitor_to_workspace(
    body: SaveCompetitorRequest,
    http_request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Keep a competitor, and its latest analysis when given, in the seller's workspace.

    The analysis's takeaway becomes the competitor's note unless the seller wrote one, so the
    ranker cites it and the seller can edit it on the competitor card. No runs, no crawls.
    """
    never_cache(response)
    account = await resolve_account(http_request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, require_binding=True)
    raw_url = body.competitor_url.strip()
    if is_social_link(raw_url):
        raise HTTPException(status_code=422, detail=SOCIAL_LINK_REFUSAL)
    if not raw_url.lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="Use the competitor's website address, like https://their-site.com.",
        )
    page_id: str | None = None
    if body.ad_library_url is not None:
        try:
            page_id = (
                parse_ad_library_page_id(body.ad_library_url) if body.ad_library_url.strip() else ""
            )
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err
    for attempt in (1, 2):
        ws = await load_workspace(account)
        version = int(ws.get("version") or 0)
        try:
            doc, entry, added = merge_saved_competitor(
                ws.get("document") or {},
                url=raw_url,
                name=body.name,
                brief=body.brief,
                ad_library_page_id=page_id,
                now_iso=now_iso_utc(),
            )
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err
        try:
            saved = await save_workspace(
                account, doc, expected_version=version, expected_owner=account.user_id
            )
        except HTTPException as err:
            # Another tab saved in between: reload once and merge again.
            if err.status_code == 409 and attempt == 1:
                continue
            raise
        return {
            "saved": True,
            "added": added,
            "version": int(saved.get("version") or version + 1),
            "competitor": {
                key: entry.get(key)
                for key in (
                    "name",
                    "url",
                    "rationale",
                    "analysis_takeaway",
                    "analyzed_at",
                    "ad_library_page_id",
                )
            }
            | {
                "selected": entry.get("selected", True) is not False,
                "ad_library_url": (
                    ad_library_page_url(str(entry["ad_library_page_id"]))
                    if entry.get("ad_library_page_id")
                    else None
                ),
            },
        }
    raise HTTPException(status_code=409, detail="Your workspace changed. Reload and try again.")


@router.post("/analyze-competitors", response_model=CompetitorBrief)
async def analyze_competitors(
    request: CompetitorIntelRequest,
    service: Annotated[CompetitorIntelService, Depends(get_competitor_intel_service)],
    live: LiveMode,
    response: Response,
) -> CompetitorBrief:
    # A Meta Ad Library search or a social page is not a competitor's website. Refuse it before
    # any crawl; a refused live request finishes as failed, so the run is given back.
    if is_social_link(request.competitor_url):
        raise HTTPException(status_code=422, detail=SOCIAL_LINK_REFUSAL)
    if not live:
        return demo.demo_competitor_brief_for(request.competitor_url)
    return await result_cache.cached(
        "analyze-competitors",
        request,
        CompetitorBrief,
        lambda: service.analyze(request),
        response,
        fallback=lambda: demo.demo_competitor_brief_for(request.competitor_url),
    )


@router.post("/audit-seller", response_model=SellerFootprintAudit | SellerDiagnostics)
async def audit_seller(
    request: AuditSellerRequest,
    live: LiveMode,
    response: Response,
) -> SellerFootprintAudit | SellerDiagnostics:
    if request.deterministic_only or not live:
        return compute_seller_diagnostics(request.profile)
    return await result_cache.cached(
        "audit-seller",
        request,
        SellerFootprintAudit,
        lambda: audit_seller_footprint(request.profile, competitor_brief=request.competitor_brief),
        response,
        fallback=lambda: compute_seller_diagnostics(request.profile),
    )


SCAN_CACHE_HEADER = "X-Muse-Scan-Cache"
BLOCKED_SCAN_HOSTS = ("instagram.com", "facebook.com", "saatchiart.com", "etsy.com")


def scan_url(raw_url: str) -> tuple[str, str, bool]:
    """(address to crawl, host, whether the host refuses automated reading)."""
    normalized = raw_url if "://" in raw_url else f"https://{raw_url.lstrip('@')}"
    host = (urlparse(normalized).hostname or "").lower()
    return normalized, host, any(name in host for name in BLOCKED_SCAN_HOSTS)


def reserve_scan_crawls(
    http_request: Request, response: Response, urls: list[str], max_urls: int
) -> None:
    """Refuse a public scan with 429 before any crawl when the visitor is over the cap.

    Both public scans (this route and /seller-memory/scan) call it with every address they would
    crawl. The cap and the cache in src/services/scan_guard.py are off unless configured.
    """
    fresh = scan_guard.fresh_count(urls, max_urls)
    retry_after = scan_guard.reserve_scans(_client_ip_hash(http_request), fresh)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=scan_guard.refusal_message(retry_after),
            headers={"Retry-After": str(retry_after)},
        )
    if fresh < len(urls):
        response.headers[SCAN_CACHE_HEADER] = f"{len(urls) - fresh}/{len(urls)}"


@router.post("/ingest-storefront")
async def ingest_storefront(
    request: IngestStorefrontRequest, http_request: Request, response: Response
) -> dict[str, Any]:
    """Crawl a seller's own website & marketplace pages to build a live reference profile.

    Public, because setup and the editors use it before sign-in; see reserve_scan_crawls.
    """
    sources: list[tuple[str, str]] = []
    if request.website_url.strip():
        sources.append(("own_website", request.website_url.strip()))
    for m_url in request.marketplace_urls:
        if m_url.strip():
            sources.append(("marketplace", m_url.strip()))
    for s_url in request.social_urls:
        if s_url.strip():
            sources.append(("social", s_url.strip()))

    targets = [(kind, raw_url, *scan_url(raw_url)) for kind, raw_url in sources]
    reserve_scan_crawls(
        http_request,
        response,
        [normalized for _, _, normalized, _, blocked in targets if not blocked],
        request.max_urls_per_source,
    )

    channel_results: list[dict[str, Any]] = []
    discovered_items: list[dict[str, Any]] = []
    price_hints: list[str] = []

    for kind, raw_url, normalized, host, blocked in targets:
        if blocked:
            channel_results.append(
                {
                    "kind": kind,
                    "url": raw_url,
                    "host": host,
                    "status": "vision_or_manual",
                    "pages_found": 0,
                    "note": (
                        f"{host} does not allow automated reading, so Muse did not scan it. "
                        "Add items from it yourself."
                    ),
                }
            )
            continue

        try:
            entries, sitemaps = await scan_guard.crawl(
                normalized,
                request.max_urls_per_source,
                lambda normalized=normalized: collect_entries(
                    normalized,
                    fetch_titles=True,
                    max_urls=request.max_urls_per_source,
                    max_title_fetches=12,
                ),
            )
            channel_results.append(
                {
                    "kind": kind,
                    "url": normalized,
                    "host": host,
                    "status": "fetched",
                    "pages_found": len(entries),
                    "sitemaps": sitemaps,
                    "note": f"Crawled {len(entries)} allowed pages/listings from {host}.",
                }
            )
            for entry in entries[:15]:
                if entry.price_hint and entry.price_hint not in price_hints:
                    price_hints.append(entry.price_hint)
                discovered_items.append(
                    {
                        "url": entry.loc,
                        "title": entry.title or entry.loc.rsplit("/", 1)[-1],
                        "bucket": entry.bucket,
                        "price_hint": entry.price_hint,
                    }
                )
        except SitemapError as err:
            channel_results.append(
                {
                    "kind": kind,
                    "url": normalized,
                    "host": host,
                    "status": "vision_or_manual",
                    "pages_found": 0,
                    "note": str(err),
                }
            )

    sample_titles = [item["title"] for item in discovered_items[:10] if item.get("title")]
    channels_str = ", ".join(f"{c['host']} ({c['status']})" for c in channel_results)
    prices_str = (
        ", ".join(price_hints[:6]) if price_hints else "No public prices detected on crawled pages"
    )
    scan_date = datetime.now(UTC).date().isoformat()
    seller_context = (
        f"{request.business_name}. Connected channels: {channels_str}. "
        f"Sample catalog pages/products: {'; '.join(sample_titles[:8]) or 'None indexed yet'}. "
        f"Detected price points: {prices_str}."
    )

    suggested_socials = extract_social_handles(
        {
            "social_urls": request.social_urls,
            "channels": channel_results,
            "items": discovered_items,
        }
    )

    return {
        "business_name": request.business_name,
        "scan_date": scan_date,
        "total_channels": len(channel_results),
        "total_pages_crawled": sum(int(c["pages_found"]) for c in channel_results),
        "channels": channel_results,
        "discovered_catalog_items": discovered_items[:24],
        "detected_price_hints": price_hints,
        "seller_context": seller_context,
        "suggested_socials": suggested_socials,
    }


@router.post("/audit-screenshot", response_model=ScreenshotAnalysis)
async def audit_screenshot(
    request: ScreenshotAuditRequest, live: LiveMode, response: Response
) -> ScreenshotAnalysis:
    """Run Muse Spark 1.3 Vision on an uploaded IG, FB, Saatchi, Etsy, or website screenshot."""
    if not live:
        raise demo_unavailable("Screenshot analysis")
    raw = request.image_base64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(raw, validate=True)
    except binascii.Error as err:
        raise MetaAPIError("Upload the screenshot again: the image data was not valid.") from err
    return await result_cache.cached(
        "audit-screenshot",
        request,
        ScreenshotAnalysis,
        lambda: analyze_social_screenshots([img_bytes], context=request.context),
        response,
    )


class CompetitorCheckRequest(BaseModel):
    expected_version: int | None = None
    expected_owner: str | None = None


class WatchlistAutoCheckRequest(BaseModel):
    paused: bool


WATCHLIST_RUN_MAX_SECONDS = 280.0
WATCHLIST_WORST_CASE_SELLER_SECONDS = MAX_COMPETITORS_PER_CHECK * PER_SITE_CRAWL_TIMEOUT_SECONDS
WATCHLIST_RUN_BUDGET_SECONDS = WATCHLIST_RUN_MAX_SECONDS - WATCHLIST_WORST_CASE_SELLER_SECONDS
WATCHLIST_LEASE_SECONDS = 600


def _merge_previous_snapshots(
    table_data: dict[str, Any] | None, legacy_checks: Any
) -> dict[str, Any]:
    """Build per-URL previous snapshot map: table first, legacy workspace fallback."""
    merged: dict[str, Any] = {}
    if isinstance(legacy_checks, dict):
        for raw_key, val in legacy_checks.items():
            if not isinstance(val, dict):
                continue
            key = normalize_competitor_url(str(raw_key or val.get("url") or ""))
            if key:
                merged[key] = val
    if isinstance(table_data, dict) and table_data.get("enabled"):
        for key, val in (table_data.get("checks") or {}).items():
            if isinstance(val, dict):
                merged[key] = val
    return merged


@router.get("/competitors/checks")
async def get_own_competitor_checks(
    http_request: Request,
    response: Response,
) -> dict[str, Any]:
    """Return the signed-in seller's saved competitor checks (display-only, no snapshots)."""
    never_cache(response)
    account = await resolve_account(http_request, response, require_verified=True)
    assert account is not None

    ws = await load_workspace(account)
    doc = ws.get("document") if isinstance(ws.get("document"), dict) else {}
    prefs = doc.get("preferences") if isinstance(doc.get("preferences"), dict) else {}
    legacy_checks = prefs.get("competitor_checks")

    table_data = (
        await watchlist_store.get_checks(account.user_id, with_snapshots=False)
        if watchlist_store.auto_check_enabled()
        else None
    )
    merged, auto_check = watchlist_store.merge_checks_for_display(table_data, legacy_checks)
    return {
        "competitor_checks": merged,
        "auto_check": auto_check,
    }


@router.post("/competitors/auto-check")
async def set_own_watchlist_auto_check(
    body: WatchlistAutoCheckRequest,
    http_request: Request,
    response: Response,
) -> dict[str, Any]:
    """Pause or resume weekly automatic watchlist checks for the signed-in seller."""
    response.headers["Cache-Control"] = "no-store"
    if not watchlist_store.auto_check_enabled():
        raise HTTPException(status_code=404, detail="Automatic watchlist checks are not enabled.")
    account = await resolve_account(http_request, response, require_verified=True)
    assert account is not None

    sched = await watchlist_store.set_paused(account.user_id, body.paused)
    return {
        "auto_check": {
            "enabled": True,
            "paused": bool(sched.get("paused", body.paused)),
            "next_check_at": sched.get("next_check_at"),
            "last_auto_check_at": sched.get("last_auto_check_at"),
        }
    }


@router.post("/competitors/check")
async def check_own_competitors(
    http_request: Request,
    response: Response,
    body: CompetitorCheckRequest | None = None,
) -> dict[str, Any]:
    """Free check of the signed-in seller's own watchlist against saved page snapshots.

    Uses `reserve_scan_crawls` and `scan_guard.crawl` (capped at 6 competitors x 30 pages).
    Zero Muse calls and zero runs used.
    """
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(http_request, response, require_verified=True)
    assert account is not None

    req = body or CompetitorCheckRequest()
    if req.expected_owner and req.expected_owner != account.user_id:
        raise HTTPException(status_code=409, detail="Workspace owner mismatch.")

    ws = await load_workspace(account)
    ws_version = int(ws.get("version") or 0)
    if req.expected_version is not None and req.expected_version != ws_version:
        raise HTTPException(
            status_code=409,
            detail="Your workspace changed in another tab. Reload and check again.",
        )

    doc = dict(ws.get("document") or {})
    selected = extract_selected_competitors(doc)
    checked_at = now_iso_utc()
    use_table = watchlist_store.auto_check_enabled()

    if not selected:
        if use_table:
            sched = await watchlist_store.save_checks(
                account.user_id, source="manual", checks=[], keep_urls=[]
            )
            return {
                "checked_at": checked_at,
                "version": ws_version,
                "competitors": [],
                "top_insight": {
                    "kind": "empty",
                    "title": "Add competitors to start checking for changes",
                    "body": "Add up to 6 competitor websites in setup or your watchlist.",
                },
                "competitor_checks": {},
                "auto_check": {
                    "enabled": True,
                    "paused": bool(sched.get("paused", False)),
                    "next_check_at": sched.get("next_check_at"),
                    "last_auto_check_at": sched.get("last_auto_check_at"),
                },
            }
        return {
            "checked_at": checked_at,
            "version": ws_version,
            "competitors": [],
            "top_insight": {
                "kind": "empty",
                "title": "Add competitors to start checking for changes",
                "body": "Add up to 6 competitor websites in setup or your watchlist.",
            },
            "competitor_checks": (
                doc.get("preferences", {}).get("competitor_checks", {})
                if isinstance(doc.get("preferences"), dict)
                else {}
            ),
        }

    targets = [(item["name"], item["url"], *scan_url(item["url"])) for item in selected]
    reserve_scan_crawls(
        http_request,
        response,
        [normalized for _, _, normalized, _, blocked in targets if not blocked],
        MAX_PAGES_PER_COMPETITOR,
    )

    prefs = dict(doc.get("preferences") or {}) if isinstance(doc.get("preferences"), dict) else {}
    legacy_checks = (
        dict(prefs.get("competitor_checks") or {})
        if isinstance(prefs.get("competitor_checks"), dict)
        else {}
    )

    if use_table:
        try:
            table_data = await watchlist_store.get_checks(
                account.user_id, with_snapshots=True, raise_on_error=True
            )
        except SupabaseError as err:
            raise HTTPException(
                status_code=503,
                detail="Muse couldn't check your watchlist right now. Try again in a few minutes.",
            ) from err
        if table_data is None:
            raise HTTPException(
                status_code=503,
                detail="Muse couldn't check your watchlist right now. Try again in a few minutes.",
            )
        existing_checks = _merge_previous_snapshots(table_data, legacy_checks)
    else:
        existing_checks = legacy_checks

    results, stored_by_url, _pages_fetched = await run_watchlist_checks(
        selected,
        existing_checks,
        checked_at=checked_at,
        scan_url_fn=scan_url,
        collect_entries_fn=collect_entries,
        source="manual",
    )

    active_keys = [normalize_competitor_url(item["url"]) for item in selected]
    active_key_set = set(active_keys)
    pruned_checks = {k: v for k, v in stored_by_url.items() if k in active_key_set}
    top_insight = compute_top_insight(results, checked_at)

    if use_table:
        rows = watchlist_store.build_db_check_rows(results, pruned_checks)
        sched = await watchlist_store.save_checks(
            account.user_id,
            source="manual",
            checks=rows,
            keep_urls=active_keys,
        )
        display_checks = {
            k: {fk: fv for fk, fv in v.items() if fk != "pages"} for k, v in pruned_checks.items()
        }
        return {
            "checked_at": checked_at,
            "version": ws_version,
            "competitors": results,
            "top_insight": top_insight,
            "competitor_checks": display_checks,
            "auto_check": {
                "enabled": True,
                "paused": bool(sched.get("paused", False)),
                "next_check_at": sched.get("next_check_at"),
                "last_auto_check_at": sched.get("last_auto_check_at"),
            },
        }

    # Flag off: keep exact legacy workspace persistence behavior.
    merged_legacy = {**legacy_checks, **stored_by_url}
    pruned_legacy = {k: v for k, v in merged_legacy.items() if k in active_key_set}
    prefs["competitor_checks"] = pruned_legacy
    doc["preferences"] = prefs

    saved = await save_workspace(
        account,
        doc,
        expected_version=ws_version,
        expected_owner=account.user_id,
    )
    new_version = int(saved.get("version") or (ws_version + 1))
    return {
        "checked_at": checked_at,
        "version": new_version,
        "competitors": results,
        "top_insight": top_insight,
        "competitor_checks": pruned_legacy,
    }


@router.get("/watchlist/run")
async def run_scheduled_watchlist_checks(
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Scheduled daily Vercel Cron endpoint that checks due sellers' watchlists once a week.

    Strict CRON_SECRET bearer auth (no user-agent fallback). Logs and returns counts only.
    """
    never_cache(response)
    if not watchlist_store.auto_check_enabled():
        raise HTTPException(status_code=404, detail="Automatic watchlist checks are not enabled.")

    cron_secret = (os.environ.get("CRON_SECRET") or "").strip()
    expected_auth = f"Bearer {cron_secret}"
    if (
        not cron_secret
        or not authorization
        or not hmac.compare_digest(authorization.strip(), expected_auth)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")

    started = time.monotonic()
    per_run = max(1, min(int(get_settings().watchlist_auto_check_accounts_per_run or 10), 50))
    sellers = await watchlist_store.claim_due(limit=per_run, lease_seconds=WATCHLIST_LEASE_SECONDS)

    sellers_checked = 0
    sites_checked = 0
    errors = 0
    skipped_unconfirmed = 0
    stopped_for_budget = False

    for seller in sellers:
        if time.monotonic() - started >= WATCHLIST_RUN_BUDGET_SECONDS:
            stopped_for_budget = True
            break

        user_id = str(seller.get("user_id") or "").strip()
        if not user_id:
            continue

        try:
            confirmed = await watchlist_store.is_email_confirmed(user_id)
            if not confirmed:
                await watchlist_store.save_checks(user_id, source="auto", checks=[], keep_urls=[])
                skipped_unconfirmed += 1
                continue

            doc = await watchlist_store.load_workspace_document(user_id)
            if doc is None:
                doc = {
                    "onboarding": seller.get("onboarding") or {},
                    "preferences": seller.get("preferences") or {},
                }

            selected = extract_selected_competitors(doc)
            if not selected:
                await watchlist_store.save_checks(user_id, source="auto", checks=[], keep_urls=[])
                sellers_checked += 1
                continue

            legacy_checks = (
                doc.get("preferences", {}).get("competitor_checks")
                if isinstance(doc.get("preferences"), dict)
                else None
            )
            table_data = await watchlist_store.get_checks(
                user_id, with_snapshots=True, raise_on_error=True
            )
            if table_data is None:
                raise RuntimeError("Watchlist table read unavailable")
            existing_checks = _merge_previous_snapshots(table_data, legacy_checks)

            checked_at = now_iso_utc()
            results, stored_by_url, _pages = await run_watchlist_checks(
                selected,
                existing_checks,
                checked_at=checked_at,
                scan_url_fn=scan_url,
                collect_entries_fn=collect_entries,
                source="auto",
            )
            keep_urls = [normalize_competitor_url(item["url"]) for item in selected]
            rows = watchlist_store.build_db_check_rows(results, stored_by_url)
            await watchlist_store.save_checks(
                user_id,
                source="auto",
                checks=rows,
                keep_urls=keep_urls,
            )
            sellers_checked += 1
            sites_checked += len(results)
        except Exception:
            errors += 1

    logger.info(
        "Watchlist auto-check run finished: sellers_checked=%d sites_checked=%d "
        "skipped_unconfirmed=%d errors=%d stopped_for_budget=%s",
        sellers_checked,
        sites_checked,
        skipped_unconfirmed,
        errors,
        stopped_for_budget,
    )
    return {
        "sellers_checked": sellers_checked,
        "sites_checked": sites_checked,
        "skipped_unconfirmed": skipped_unconfirmed,
        "errors": errors,
        "stopped_for_budget": stopped_for_budget,
    }


@router.get("/competitors/ads", response_model=CompetitorAdSignalsResponse)
async def get_competitor_ads(
    request: Request,
    query: str = Query(
        ..., min_length=1, max_length=100, description="Competitor brand or page name"
    ),
    force_refresh: bool = Query(False, description="Bypass research cache"),
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> CompetitorAdSignalsResponse:
    """Fetch competitor active ads from Meta Ad Library with Track E caching.

    Rules:
    - If no META_ADS_ACCESS_TOKEN is configured: returns no_token status with
      link-out only, zero fabricated rows.
    - If token is configured: queries MetaAdLibraryClient, caches results (Track E),
      distinguishes API zero from failure.
    - API zero: returns "No ads found via the Meta API."
    - API failure: returns graceful error note with link-out.
    """
    cfg = settings or get_settings()
    public_url = build_ad_library_search_url(query)
    token = cfg.meta_ads_access_token.strip()

    if not token:
        return CompetitorAdSignalsResponse(
            query=query,
            public_library_url=public_url,
            status="no_token",
            message="Meta Ad Library access token is not configured on this server.",
            total_active_ads=0,
            ads=[],
            is_cached=False,
        )

    account = await resolve_account(request, None, require_verified=False)
    if not account:
        return CompetitorAdSignalsResponse(
            query=query,
            public_library_url=public_url,
            status="no_token",
            message="Sign in to query live Meta Ad Library signals. Public link available.",
            total_active_ads=0,
            ads=[],
            is_cached=False,
        )
    account_id = account.user_id

    async def _fetch() -> SocialCompetitorSignals:
        client = MetaAdLibraryClient(settings=cfg)
        try:
            return await client.search_active_ads(query)
        finally:
            await client.aclose()

    try:
        signals, is_hit, cache_label = await cached_research(
            NAMESPACE_AD_PREVIEWS,
            account_id,
            query,
            SocialCompetitorSignals,
            _fetch,
            force_refresh=force_refresh,
        )
    except Exception as err:
        logger.warning("Ad Library search failed for '%s': %s", query, err)
        return CompetitorAdSignalsResponse(
            query=query,
            public_library_url=public_url,
            status="error",
            message=f"Meta Ad Library request failed: {type(err).__name__}",
            total_active_ads=0,
            ads=[],
            is_cached=False,
        )

    if signals.total_active_ads == 0:
        return CompetitorAdSignalsResponse(
            query=query,
            public_library_url=public_url,
            status="zero",
            message="No ads found via the Meta API.",
            total_active_ads=0,
            ads=[],
            is_cached=is_hit,
            cache_label=cache_label,
        )

    return CompetitorAdSignalsResponse(
        query=query,
        public_library_url=public_url,
        status="live",
        message=f"Found {signals.total_active_ads} active ads via Meta Ad Library API.",
        total_active_ads=signals.total_active_ads,
        ads=signals.top_longevity_ads,
        is_cached=is_hit,
        cache_label=cache_label,
    )


def _read_sample_json(filename: str) -> dict[str, Any]:
    path = SAMPLES_DIR / filename
    if not path.is_file():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")))


@router.get("/demo-presets")
async def get_demo_presets(response: Response) -> dict[str, Any]:
    """Return pre-verified live demo data for the Customer Portal (Art of Sarabjit Singh + Etsy)."""
    cache_for_everyone(response)
    profile_raw = _read_sample_json("sarabjit_singh_profile.json")
    diagnostics_dict: dict[str, Any] = {}
    if profile_raw:
        profile_obj = SellerProfile.model_validate(profile_raw)
        diagnostics_dict = compute_seller_diagnostics(profile_obj).model_dump(mode="json")

    comp_brief = _read_sample_json("competitor_brief_sikhiart_live.json")
    if comp_brief and not comp_brief.get("research_brief"):
        comp_brief["research_brief"] = {
            "competitor_domain": "www.sikhiart.com",
            "pages_fetched": 12,
            "findings": [
                {
                    "finding_id": "F1",
                    "category": "pricing",
                    "claim": (
                        "Competitor entry print starts at $59.99 (up to $2,499.99 canvas), "
                        "leaving the $14-$25 Gurpurab starter gift & $75 signed 18k-gold tier open."
                    ),
                    "implication": (
                        "Highlight $22 starter prints for gift buyers and $75 signed 18k-gold "
                        "editions for serious collectors."
                    ),
                    "confidence": "high",
                    "evidence": [
                        {
                            "url": "computed_signals",
                            "quote": "detected_price_hints: $59.99 - $2499.99",
                        }
                    ],
                },
                {
                    "finding_id": "F2",
                    "category": "catalog_gap",
                    "claim": (
                        "Zero collection pages for Sikh Women, Punjabi Village Life, "
                        "Goddess series, or epoxy resin functional art across 8 collections."
                    ),
                    "implication": (
                        "Launch dedicated 'Sikh Women & Heritage' and 'Punjabi Village Life' "
                        "collector collections and ad sets."
                    ),
                    "confidence": "high",
                    "evidence": [
                        {
                            "url": "computed_signals",
                            "quote": "bucket_counts: collections=8, blogs=2",
                        }
                    ],
                },
                {
                    "finding_id": "F3",
                    "category": "positioning",
                    "claim": (
                        "Every product title appends 'for Your Home' and uses 'First/Second "
                        "Edition' scarcity tags, whereas museum exhibition credentials are absent."
                    ),
                    "implication": (
                        "Lead with Triton Museum & Kala Sangam UK exhibition provenance plus "
                        "'for Your Home' collector search phrases."
                    ),
                    "confidence": "high",
                    "evidence": [
                        {
                            "url": "https://www.sikhiart.com/sitemap.xml",
                            "quote": "total_urls=300, products=57",
                        }
                    ],
                },
                {
                    "finding_id": "F4",
                    "category": "cadence",
                    "claim": (
                        "Slow release cadence (2 items in 30d, 0.23/week), focused on "
                        "re-releasing warrior portraits (Mai Bhago ji, Hari Singh Nalwa)."
                    ),
                    "implication": (
                        "Avoid head-to-head bidding on warrior portrait keywords; shift budget "
                        "to high-ROAS site-visitor retargeting and Guru Nanak 550th series."
                    ),
                    "confidence": "medium",
                    "evidence": [
                        {
                            "url": "computed_signals",
                            "quote": "recent_30d_count=2, publishing_cadence_per_week=0.23",
                        }
                    ],
                },
            ],
        }

    ads_path = SAMPLES_DIR / "art_competitor_meta_ads.json"
    ad_signals = (
        load_sample_ad_library_signals(ads_path).model_dump(mode="json")
        if ads_path.is_file()
        else {}
    )
    ad_signals["is_sample"] = True
    ad_signals["sample_hooks"] = [
        (
            "[sample] Desi Canvas Co (81d active on IG+FB): "
            "'Golden Temple Sunset Framed Canvas — Ready to Hang' ($129+)"
        ),
        (
            "[sample] Punjab Heritage Prints (44d active on IG): "
            "'3-Piece Sikh History Collector Set — Save 20%' (room mockup hook)"
        ),
        (
            "[sample] Modern South Asian Decor (9d active on IG): "
            "'Housewarming & Wedding Art Gifts Under $95'"
        ),
    ]

    return {
        "active_workspace": "sarabjit_singh",
        "workspaces": {
            "sarabjit_singh": {
                "id": "sarabjit_singh",
                "name": "Art of Sarabjit Singh",
                "owner": "Sarabjit Singh",
                "category": "Fine Artist & Multi-Channel Creator",
                "location": "San Francisco Bay Area, CA",
                "avatar_initials": "SS",
                "website_url": "https://www.artofsarabjitsingh.com/",
                "instagram_handle": "@artofsarabjitsingh",
                "profile": profile_raw,
                "diagnostics": diagnostics_dict,
                "competitor_brief": comp_brief,
                "meta_ads_signals": ad_signals,
                "creative_live": _read_sample_json("ad_creative_ek_onkar_live.json"),
                "bid_advice_live": _read_sample_json("bid_advice_live.json"),
                "campaign_raw": _read_sample_json("sarabjit_singh_campaign.json"),
                "artworks_showcase": [
                    {
                        "id": "ek_onkar",
                        "title": "1. Product Visuals: Ek Onkar (18k Gold Signed Edition)",
                        "subtitle": "Muse Image 1.0 Product Visuals · Mirrors ComfyUI Krea Scene",
                        "workflow_mode": "product_visuals",
                        "series": "Guru Nanak Dev 550th Anniversary",
                        "medium": "Acrylic & 18k gold ink on canvas / archival giclee",
                        "price_pod_usd": 14.0,
                        "price_direct_usd": 75.0,
                        "price_large_usd": 125.0,
                        "original_image": "/samples/ek_onkar_original.jpg",
                        "staged_image": "/samples/ek_onkar_collector_room_live.webp",
                        "mask_image": "/samples/ek_onkar_original.jpg",
                        "exhibited_at": "Triton Museum of Art · Kala Sangam UK · Sikhlens LA",
                        "headline": "Ek Onkar in 18k Gold ✨ Signed Edition of 100",
                        "primary_text": (
                            "550 years of Light. One sacred word — Ek Onkar. Hand-embellished "
                            "with 18k gold ink, signed & numbered by Bay Area artist Sarabjit "
                            'Singh. Exhibited at Triton Museum & Kala Sangam UK. 12x12" $75 / '
                            '24x24" $125.'
                        ),
                        "scene_prompt": (
                            "Serene modern collector living room in warm neutrals, matte off-white "
                            "gallery wall with soft museum spotlight from above, slim matte black "
                            "gallery frame with wide white mat, light oak console below with small "
                            "lit brass diya and white orchid vase"
                        ),
                        "reasoning_summary": (
                            "**Composing collector living room** — Staging the square Ek Onkar "
                            "canvas at eye level in a slim matte black frame with museum "
                            "spotlighting, oak console, lit brass diya, and white orchids while "
                            "preserving every brushstroke."
                        ),
                    },
                    {
                        "id": "diptych_combine",
                        "title": "2. Multi-Image Combine: Ek Onkar + Kirat Karo Diptych Set",
                        "subtitle": (
                            "Muse Image 1.0 Multi-Image (/v1/responses) · Mirrors Krea-2 Multi-Ref"
                        ),
                        "workflow_mode": "multi_image_combine",
                        "series": "Guru Nanak Dev 550th Anniversary Collector Bundle",
                        "medium": "Matched 2-Piece Signed 18k Gold Collector Diptych",
                        "price_pod_usd": 31.0,
                        "price_direct_usd": 135.0,
                        "price_large_usd": 225.0,
                        "original_image": "/samples/ek_onkar_original.jpg",
                        "secondary_image": "/samples/kirat_karo_original.jpg",
                        "staged_image": "/samples/diptych_ek_onkar_kirat_karo_live.webp",
                        "mask_image": "/samples/ek_onkar_original.jpg",
                        "exhibited_at": (
                            "Counter-positions 44d Competitor Winner ('Collector Set - Save 20%')"
                        ),
                        "headline": "2-Piece Guru Nanak 550th Collector Diptych ✨ Save $15",
                        "primary_text": (
                            "Pair Ek Onkar and Kirat Karo side by side above your console or sofa. "
                            "Both hand-signed & numbered by Sarabjit Singh (Edition of 100). "
                            '2-piece 12x12" collector set $135 (or 24x24" set $225).'
                        ),
                        "scene_prompt": (
                            "Combine these two square Sikh heritage paintings side by side as a "
                            "matched framed collector diptych hanging on a warm sunlit plaster "
                            "gallery wall above a walnut console table with a brass diya and "
                            "white orchids. Preserve every brushstroke of both paintings."
                        ),
                        "reasoning_summary": (
                            "**Assembling heritage diptych display** — Arranging the two square "
                            "Sikh heritage paintings side by side in matching slim black frames on "
                            "a warm sunlit plaster wall above a walnut console with a brass diya "
                            "and white orchids, preserving every brushstroke."
                        ),
                    },
                    {
                        "id": "naam_japo",
                        "title": "3. Restore Image: Naam Japo (Meditation) Studio Enhance",
                        "subtitle": (
                            "Muse Image 1.0 Restore Image (/v1/responses) · Mirrors 4x-UltraSharp"
                        ),
                        "workflow_mode": "restore_enhance",
                        "series": "Guru Nanak Dev 550th Anniversary",
                        "medium": "Acrylic on canvas (Original Sold) · Signed Edition of 100",
                        "price_pod_usd": 17.0,
                        "price_direct_usd": 75.0,
                        "price_large_usd": 125.0,
                        "original_image": "/samples/naam_japo_original.jpg",
                        "staged_image": "/samples/naam_japo_restored_gallery_live.webp",
                        "mask_image": "/samples/naam_japo_original.jpg",
                        "exhibited_at": "Triton Museum of Art · Kala Sangam Gallery UK",
                        "headline": "The Original Sold — Own one of 100 Signed 18k Gold Prints",
                        "primary_text": (
                            "Naam Japo (Meditation) from the Guru Nanak 550th Anniversary series. "
                            "Original canvas is in a private collection—now available as a "
                            "hand-signed, numbered 18k gold-embellished archival print."
                        ),
                        "scene_prompt": (
                            "Restore this painting image with crisp studio lighting, rich acrylic "
                            "texture detail, and higher resolution, framed in a warm natural oak "
                            "floating gallery frame mounted above a serene linen meditation bench "
                            "with morning sunlight streaming across the wall."
                        ),
                        "reasoning_summary": (
                            "**Restoring painting with framing** — Keeping every brushstroke of "
                            "the original painting untouched, placing it in a warm natural oak "
                            "floating frame above a linen meditation bench with crisp studio "
                            "lighting and morning sunlight across the wall."
                        ),
                    },
                    {
                        "id": "kirat_karo",
                        "title": "4. Image Edit: Kirat Karo (Brushed-Brass Dining Room)",
                        "subtitle": (
                            "Muse Image 1.0 Image Edit (/v1/images/edits) · Mirrors FLUX Relight"
                        ),
                        "workflow_mode": "product_visuals",
                        "series": "Guru Nanak Dev 550th Anniversary",
                        "medium": "Acrylic on canvas / hand-signed giclee",
                        "price_pod_usd": 17.0,
                        "price_direct_usd": 75.0,
                        "price_large_usd": 125.0,
                        "original_image": "/samples/kirat_karo_original.jpg",
                        "staged_image": "/samples/kirat_karo_collector_room_live.webp",
                        "mask_image": "/samples/kirat_karo_original.jpg",
                        "exhibited_at": "Triton Museum of Art · Faiz Art Festival Lahore",
                        "headline": "Kirat Karo — Sacred Punjabi Heritage for Your Dining Room",
                        "primary_text": (
                            "Celebrate the dignity of honest work and Punjabi roots. Signed & "
                            "numbered collector edition by Sarabjit Singh, ready to frame above "
                            "your dining table or study."
                        ),
                        "scene_prompt": (
                            "Warm California contemporary dining room wall in soft cream plaster, "
                            "warm museum picture light in brushed brass mounted above a dark "
                            "walnut mid-century sideboard with a terracotta ceramic vase holding "
                            "olive branches"
                        ),
                        "reasoning_summary": (
                            "**Staging dining room gallery wall** — Framing Kirat Karo under a "
                            "warm brushed-brass picture light above a walnut mid-century sideboard "
                            "with olive branches."
                        ),
                    },
                ],
            },
            "etsy_ceramics": {
                "id": "etsy_ceramics",
                "name": "Saffron & Clay Studio",
                "owner": "Meera & Kabir Crafts",
                "category": "Etsy Physical Goods & Handmade Home Decor",
                "location": "Austin, TX · Etsy Star Seller",
                "avatar_initials": "SC",
                "website_url": "https://www.saffronandclay.com/",
                "marketplace_urls": "https://www.etsy.com/shop/SaffronAndClayStudio",
                "instagram_handle": "@saffronandclay",
                "diagnostics": {
                    "total_platforms": 4,
                    "total_artworks_indexed": 48,
                    "artworks_missing_series_tag": 14,
                    "artworks_missing_original_price": 6,
                    "has_direct_checkout_gap": False,
                },
                "competitor_brief": {
                    "competitor_domain": "www.eastfork.com",
                    "summary": (
                        "Competitor sells modern minimalist ceramic mug sets ($44-$160) but has "
                        "zero South Asian heritage brass/stoneware chai sets or ready-to-gift "
                        "Diwali/Wedding host boxes under $65."
                    ),
                    "research_brief": {
                        "competitor_domain": "www.eastfork.com",
                        "pages_fetched": 18,
                        "findings": [
                            {
                                "finding_id": "F1",
                                "category": "pricing",
                                "claim": (
                                    "Competitor 2-mug sets start at $88 with $12 shipping; no "
                                    "sub-$58 gift-boxed chai set exists in their catalog."
                                ),
                                "implication": (
                                    "Position the $54 2-Piece Stoneware & Hammered Brass Chai Set "
                                    "with free gift wrap as the #1 housewarming & wedding gift."
                                ),
                                "confidence": "high",
                                "evidence": [
                                    {
                                        "url": "computed_signals",
                                        "quote": "detected_price_hints: $44 - $160",
                                    }
                                ],
                            },
                            {
                                "finding_id": "F2",
                                "category": "catalog_gap",
                                "claim": (
                                    "Zero brass diya + block-printed linen bundles for Diwali, "
                                    "Gurpurab, or South Asian wedding registry shoppers."
                                ),
                                "implication": (
                                    "Launch the $68 Heirloom Brass Diya + Marigold Linen Runner "
                                    "Gift Box on Instagram Reels and Etsy Ads."
                                ),
                                "confidence": "high",
                                "evidence": [
                                    {
                                        "url": "https://www.eastfork.com/sitemap.xml",
                                        "quote": "collections=6, zero heritage gift bundles",
                                    }
                                ],
                            },
                        ],
                    },
                    "actionable_insights": [
                        {
                            "title": "Bundle Chai Cups + Whole Cardamom Spice Tin",
                            "action": (
                                "Create a $54 2-cup Gift Box SKU on Shopify & Etsy with 1-click "
                                "gift note checkout."
                            ),
                            "why": "Competitors charge $88+ for 2 mugs with no gift packaging.",
                            "priority": "high",
                        },
                        {
                            "title": "Run 9:16 Pouring-Chai Reel on Instagram",
                            "action": (
                                "Use the Muse Image 1.0 travertine chai set visual as the hero "
                                "frame for a 9:16 Reel targeting wedding/housewarming buyers."
                            ),
                            "why": "30d+ competitor ads use warm kitchen countertop lighting.",
                            "priority": "high",
                        },
                    ],
                },
                "meta_ads_signals": {
                    "is_sample": True,
                    "sample_hooks": [
                        (
                            "[sample] Artisan Table Co (62d active on IG): "
                            "'Hand-Thrown Mug Duo — Free Gift Box'"
                        ),
                        (
                            "[sample] Jaipur Living Decor (39d active on IG+FB): "
                            "'Block-Printed Table Runners 20% Off'"
                        ),
                    ],
                },
                "bid_advice_live": _read_sample_json("bid_advice_live.json"),
                "campaign_raw": _read_sample_json("sarabjit_singh_campaign.json"),
                "artworks_showcase": [
                    {
                        "id": "chai_set",
                        "title": "1. Product Visuals: Stoneware & Brass Masala Chai Set",
                        "subtitle": (
                            "Muse Image 1.0 Product Visuals (/v1/responses · High Reasoning)"
                        ),
                        "workflow_mode": "product_visuals",
                        "series": "Heirloom Kitchen & Chai Rituals",
                        "medium": "Hand-thrown speckled stoneware + hammered solid brass",
                        "price_pod_usd": 28.0,
                        "price_direct_usd": 54.0,
                        "price_large_usd": 98.0,
                        "original_image": "/samples/etsy_chai_set_product_visual_live.webp",
                        "staged_image": "/samples/etsy_chai_set_product_visual_live.webp",
                        "mask_image": "/samples/etsy_chai_set_product_visual_live.webp",
                        "exhibited_at": (
                            "Etsy Star Seller · 4.9★ (410+ Reviews) · Ships from Austin, TX"
                        ),
                        "headline": "Handcrafted Stoneware & Brass Chai Duo ✨ $54 Gift Box",
                        "primary_text": (
                            "Elevate your daily chai ritual. Hand-thrown speckled stoneware paired "
                            "with a hammered brass tumbler and saffron block-printed napkin. "
                            "Ready-to-gift box $54."
                        ),
                        "scene_prompt": (
                            "Handcrafted speckled stoneware and hammered brass masala chai cup set "
                            "on a warm sunlit travertine countertop with whole green cardamom "
                            "pods, cinnamon sticks, and a block-printed saffron linen napkin"
                        ),
                        "reasoning_summary": (
                            "**Composing sunlit chai ritual product shot** — Pairing the speckled "
                            "stoneware cup and hammered brass tumbler on warm travertine with "
                            "cardamom pods, cinnamon sticks, and a saffron block-printed napkin."
                        ),
                    },
                    {
                        "id": "diwali_gift_box",
                        "title": "2. Multi-Image Bundle: Heirloom Brass Diya + Linen Runner Box",
                        "subtitle": (
                            "Muse Image 1.0 Holiday Gift Bundle (/v1/responses · High Reasoning)"
                        ),
                        "workflow_mode": "multi_image_combine",
                        "series": "Festive Host & Housewarming Gift Boxes",
                        "medium": "Solid sand-cast brass diya + hand-block-printed marigold linen",
                        "price_pod_usd": 34.0,
                        "price_direct_usd": 68.0,
                        "price_large_usd": 115.0,
                        "original_image": "/samples/etsy_diwali_gift_box_live.webp",
                        "secondary_image": "/samples/etsy_chai_set_product_visual_live.webp",
                        "staged_image": "/samples/etsy_diwali_gift_box_live.webp",
                        "mask_image": "/samples/etsy_diwali_gift_box_live.webp",
                        "exhibited_at": (
                            "#1 Bestseller for Housewarming, Wedding & Festive Gifting"
                        ),
                        "headline": "Heirloom Brass Diya & Marigold Linen Gift Box ✨ $68",
                        "primary_text": (
                            "Unbox warmth and heritage. Includes our hand-carved solid brass diya "
                            'and 72" marigold hand-block-printed linen table runner in a keepsake '
                            "kraft gift box."
                        ),
                        "scene_prompt": (
                            "Heirloom hand-carved brass diya oil lamp paired with a block-printed "
                            "marigold linen table runner in a luxury kraft gift box with dried "
                            "jasmine flowers, warm golden hour lighting"
                        ),
                        "reasoning_summary": (
                            "**Staging luxury kraft gift bundle** — Presenting the folded marigold "
                            "block-printed linen runner inside a ribboned kraft box beside the "
                            "carved brass diya and jasmine buds in golden-hour light."
                        ),
                    },
                ],
            },
        },
    }
