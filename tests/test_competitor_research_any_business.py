"""Tests for services-aware competitor research buckets, prompts, and honest Meta Ad status."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi import HTTPException

from src.api.main import app
from src.models.intel import (
    BatchAnalysis,
    CitedInsightLLM,
    CompetitorAdSignalsResponse,
    CompetitorBriefLLMOutput,
    CompetitorIntelRequest,
    EvidenceRef,
    ResearchFindingLLM,
    SitemapEntry,
    SocialAdSummary,
)
from src.services.accounts import AccountSession
from src.services.competitor_intel import (
    BATCH_ANALYSIS_SYSTEM_PROMPT,
    BRIEF_SYNTHESIS_SYSTEM_PROMPT,
    SERVICES_BATCH_ANALYSIS_SYSTEM_PROMPT,
    SERVICES_BRIEF_SYNTHESIS_SYSTEM_PROMPT,
    _select_entries_for_title_enrichment,
    analyze_url_batches,
    build_brief,
    derive_signals,
)
from src.utils.sitemap import classify_url_bucket


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if not candidate or not os.path.exists(candidate):
            continue
        probe = subprocess.run(
            [candidate, "-c", "import playwright.sync_api"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return None


def test_classify_url_bucket_services_and_shop_sites() -> None:
    """Service/case-study URLs classify cleanly without misfiling shops or artist portfolios."""
    assert classify_url_bucket("https://firm.example/services/ai-strategy") == "services"
    assert classify_url_bucket("https://firm.example/consulting/growth-audit") == "services"
    assert classify_url_bucket("https://firm.example/advisory/gtm") == "services"
    assert classify_url_bucket("https://firm.example/solutions/revops") == "services"
    assert classify_url_bucket("https://firm.example/case-studies/acme-corp") == "case_studies"
    assert classify_url_bucket("https://firm.example/case-study/retail-launch") == "case_studies"
    assert classify_url_bucket("https://firm.example/client-stories/studio-x") == "case_studies"
    assert classify_url_bucket("https://firm.example/success-stories/growth") == "case_studies"

    # Artist / shop sites must NOT be misfiled as services or case_studies
    assert classify_url_bucket("https://artist.example/portfolio/paintings") == "other"
    assert classify_url_bucket("https://artist.example/products/ek-onkar-print") == "products"
    assert classify_url_bucket("https://shop.example/listing/12345/bowl") == "listings"
    assert classify_url_bucket("https://shop.example/collections/gifts") == "collections"
    assert classify_url_bucket("https://artist.example/galleries/sacred") == "collections"
    assert classify_url_bucket("https://artist.example/blog/painting-story") == "blogs"


def test_services_buckets_counted_and_prioritized() -> None:
    """Services and case_studies buckets are counted in signals and ranked ahead of other/pages."""
    entries = [
        SitemapEntry(loc="https://firm.example/about", bucket="pages"),
        SitemapEntry(loc="https://firm.example/misc-thing", bucket="other"),
        SitemapEntry(loc="https://firm.example/services/ai-audit", bucket="services"),
        SitemapEntry(loc="https://firm.example/case-studies/fintech", bucket="case_studies"),
    ]
    signals = derive_signals(entries, competitor_domain="firm.example")
    assert signals.bucket_counts["services"] == 1
    assert signals.bucket_counts["case_studies"] == 1
    assert "services" in signals.growing_categories
    assert "case_studies" in signals.growing_categories

    top = _select_entries_for_title_enrichment(entries, limit=2)
    assert [e.bucket for e in top] == ["services", "case_studies"]


@pytest.mark.asyncio
async def test_business_type_selects_prompts_with_null_preserving_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """business_type=None keeps exact default prompts; services uses services prompts."""
    captured_prompts: list[str] = []

    async def fake_chat_structured(*, messages: Any, response_model: Any, **kwargs: Any) -> Any:
        captured_prompts.append(messages[0]["content"])
        if response_model is BatchAnalysis:
            return BatchAnalysis(product_categories=["AI Audits"])
        return CompetitorBriefLLMOutput(
            summary="Clear services positioning with published case studies.",
            product_categories=["AI Audits"],
            pricing_signals=["Fixed-scope audit package"],
            content_strategy_patterns=["Client case studies"],
            seo_keywords=["ai growth audit"],
            new_product_frequency="2 service pages in catalog.",
            doubling_down_on=["Advisory packages"],
            competitor_gaps=["No starter offer for small teams"],
            research_brief=[
                ResearchFindingLLM(
                    finding="Publishes fixed-scope audit service.",
                    evidence=[
                        EvidenceRef(
                            source_url="https://firm.example/services/ai-audit",
                            detail="AI Audit service page",
                        )
                    ],
                    recommendation="Publish a clear entry audit page.",
                )
            ],
            actionable_insights=[
                CitedInsightLLM(
                    title="Publish a starter audit page",
                    action="Add scope and booking link on /services/audit.",
                    why="Makes starting clear.",
                    evidence=[
                        EvidenceRef(
                            source_url="https://firm.example/services/ai-audit",
                            detail="AI Audit service page",
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr("src.services.competitor_intel.chat_structured", fake_chat_structured)

    entries = [
        SitemapEntry(
            loc="https://firm.example/services/ai-audit",
            title="AI Audit Service",
            bucket="services",
        )
    ]
    signals = derive_signals(entries, competitor_domain="firm.example")

    # 1. business_type=None preserves exact default prompts
    captured_prompts.clear()
    await analyze_url_batches(entries, business_type=None)
    await build_brief(signals, entries=entries, business_type=None)
    assert captured_prompts[0] == BATCH_ANALYSIS_SYSTEM_PROMPT
    assert captured_prompts[1] == BRIEF_SYNTHESIS_SYSTEM_PROMPT

    # 2. business_type="services" uses services prompts and preserves CompetitorBrief schema
    captured_prompts.clear()
    await analyze_url_batches(entries, business_type="services")
    brief = await build_brief(signals, entries=entries, business_type="services")
    assert captured_prompts[0] == SERVICES_BATCH_ANALYSIS_SYSTEM_PROMPT
    assert captured_prompts[1] == SERVICES_BRIEF_SYNTHESIS_SYSTEM_PROMPT
    assert brief.product_categories == ["AI Audits"]
    assert (
        CompetitorIntelRequest(
            competitor_url="https://firm.example", business_type="services"
        ).business_type
        == "services"
    )


@pytest.fixture
def own_services_research_server(monkeypatch: pytest.MonkeyPatch):
    """Run FastAPI app with a signed-in services business and stubbed ads/analysis endpoints."""
    captured_analysis_reqs: list[dict[str, Any]] = []
    user = AccountSession(
        user_id="svc-res-u1",
        email="founder@nplusalpha.test",
        email_verified=True,
        access_token="tok-svc-res",
        session_id=None,
    )

    async def fake_resolve(request: Any, _response: Any = None, require_verified: bool = False):
        if request.cookies.get("muse_e2e_user") == "svc-res-u1":
            return user
        if require_verified:
            raise HTTPException(401, "Sign in required")
        return None

    async def fake_snapshot(account: AccountSession | None) -> dict[str, Any]:
        if account is None:
            return {"configured": True, "user": None, "usage": None, "live_available": False}
        return {
            "configured": True,
            "user": {"id": account.user_id, "email": account.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3},
            "runs_remaining": 3,
            "live_available": True,
        }

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        return {
            "document": {
                "onboarding": {
                    "business_name": "n Plus Alpha Consulting",
                    "business_type": "services",
                    "website_url": "https://nplusalpha.test",
                    "shop_urls": ["https://nplusalpha.test"],
                    "completed_at": "2026-11-18T10:00:00Z",
                    "competitors": [{"name": "Acme Advisory", "url": "https://acme-advisory.test"}],
                }
            },
            "version": 1,
            "owner_id": account.user_id,
        }

    async def fake_ads(
        request: Any, query: str = "", force_refresh: bool = False, settings: Any = None
    ) -> CompetitorAdSignalsResponse:
        return CompetitorAdSignalsResponse(
            query=query,
            public_library_url=f"https://www.facebook.com/ads/library/?q={query}",
            status="live",
            message="1 active ad found via Meta API.",
            total_active_ads=1,
            ads=[
                SocialAdSummary(
                    ad_id="ad-1",
                    page_name=query,
                    platforms=["instagram"],
                    days_running=42,
                    headline="Book a Strategy Call",
                    body_excerpt="Advisory for growing teams.",
                    start_date="2026-10-08",
                    library_url="https://www.facebook.com/ads/library/?id=ad-1",
                )
            ],
        )

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.snapshot", fake_snapshot)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)
    monkeypatch.setattr("src.api.intel.get_competitor_ads", fake_ads)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{port}", captured_analysis_reqs
    finally:
        server.should_exit = True
        thread.join(timeout=2)


def test_own_workspace_diagnostics_honest_ads_and_business_type_e2e(
    own_services_research_server: tuple[str, list[dict[str, Any]]],
) -> None:
    """Verify own-workspace diagnostics, honest Meta Ad status, and business_type payload."""
    pw_python = _find_playwright_python()
    if pw_python is None:
        pytest.skip("Playwright Python runtime unavailable")

    base_url, _ = own_services_research_server

    script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {base_url!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for width in (375, 1440):
                # 1. Own services workspace
                co = browser.new_context(viewport={{"width": width, "height": 844}})
                co.add_cookies([{{"name": "muse_e2e_user", "value": "svc-res-u1", "url": BASE}}])
                po = co.new_page()

                seen_ads_queries = []
                def mock_ads(route):
                    seen_ads_queries.append(route.request.url)
                    route.fulfill(
                        json={{
                            "query": "Acme Advisory",
                            "public_library_url": "https://www.facebook.com/ads/library/?q=Acme",
                            "status": "live",
                            "message": "1 active ad found.",
                            "total_active_ads": 1,
                            "ads": [
                                {{
                                    "ad_id": "ad-1",
                                    "page_name": "Acme Advisory",
                                    "platforms": ["instagram"],
                                    "days_running": 42,
                                    "headline": "Book a Strategy Call",
                                    "body_excerpt": "Advisory for growing teams.",
                                    "start_date": "2026-10-08",
                                    "library_url": "https://www.facebook.com/ads/library/?id=ad-1",
                                }}
                            ],
                        }}
                    )

                captured_live_payloads = []
                def mock_analyze(route):
                    captured_live_payloads.append(route.request.post_data_json)
                    route.fulfill(
                        json={{
                            "competitor_url": "https://acme-advisory.test",
                            "competitor_domain": "acme-advisory.test",
                            "summary": "Focused on B2B strategy audits.",
                            "product_categories": ["AI Audits"],
                            "pricing_signals": ["Fixed-fee audit"],
                            "content_strategy_patterns": ["Case studies"],
                            "seo_keywords": ["ai audit"],
                            "new_product_frequency": "2 service pages",
                            "doubling_down_on": ["Advisory"],
                            "competitor_gaps": ["No starter offer"],
                            "actionable_insights": [],
                            "research_brief": [],
                            "signals": {{
                                "competitor_domain": "acme-advisory.test",
                                "total_urls": 4,
                                "bucket_counts": {{"services": 2, "case_studies": 2}},
                                "growing_categories": ["services", "case_studies"],
                            }},
                        }}
                    )

                po.route("**/api/v1/competitors/ads**", mock_ads)
                po.route("**/api/v1/analyze-competitors?live=true", mock_analyze)

                po.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                po.wait_for_function(
                    "() => document.documentElement.dataset.museMode === 'account_own' && "
                    "(document.querySelector('#diagnosticsContainer')?.textContent || '')"
                    ".includes('n Plus Alpha Consulting') && "
                    "(document.querySelector('#metaAdsContainer')?.textContent || '')"
                    ".includes('reached the EU')"
                )
                diag_txt = po.locator("#diagnosticsContainer").inner_text()
                assert "artofsarabjitsingh.com" not in diag_txt, diag_txt
                assert "72 Artworks" not in diag_txt, diag_txt
                assert "FineArtAmerica" not in diag_txt, diag_txt

                ads_txt = po.locator("#metaAdsContainer").inner_text()
                assert "reached the EU" in ads_txt, ads_txt
                assert "Search public Meta Ad Library" in ads_txt, ads_txt
                assert "1 active ad in the EU" in ads_txt, ads_txt
                assert "42d" in ads_txt, ads_txt
                assert "—" not in ads_txt, ads_txt
                assert len(seen_ads_queries) >= 1
                assert not po.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                assert po.locator("#diagTitle").inner_text() == "Your website"
                assert "Deterministic Python" not in po.locator("body").inner_text()
                assert "Sample competitor ads" not in po.locator("#metaAdsSub").inner_text()

                # Trigger live competitor analysis and verify business_type="services" is sent
                po.locator("#sellerList .js-live-brief").first.click()
                po.wait_for_function(
                    "() => (document.querySelector('#compSummaryText')?.textContent || '')"
                    ".includes('B2B strategy audits')"
                )
                assert captured_live_payloads, "Expected live analyze-competitors POST"
                assert captured_live_payloads[0].get("business_type") == "services", (
                    captured_live_payloads[0]
                )
                co.close()

                # 1b. Hosted today: no Ad Library token on the server. Sellers see plain words,
                # never the server message, and the competitor rows get no status line.
                cn = browser.new_context(viewport={{"width": width, "height": 844}})
                cn.add_cookies([{{"name": "muse_e2e_user", "value": "svc-res-u1", "url": BASE}}])
                pn = cn.new_page()
                pn.route(
                    "**/api/v1/competitors/ads**",
                    lambda route: route.fulfill(
                        json={{
                            "query": "Acme Advisory",
                            "public_library_url": "https://www.facebook.com/ads/library/?q=Acme",
                            "status": "no_token",
                            "message": (
                                "Meta Ad Library access token is not configured on this server."
                            ),
                            "total_active_ads": 0,
                            "ads": [],
                        }}
                    ),
                )
                pn.goto(f"{{BASE}}/", wait_until="domcontentloaded")
                pn.wait_for_function(
                    "() => (document.querySelector('#metaAdsContainer')?.textContent || '')"
                    ".includes('Not counted yet')"
                )
                no_token_txt = pn.locator("#metaAdsContainer").inner_text()
                for word in ("token", "configured", "API", "server"):
                    assert word not in no_token_txt, (word, no_token_txt)
                assert "Search public Meta Ad Library" in no_token_txt, no_token_txt
                assert pn.locator("#sellerList .jr-ad-status").count() == 0
                cn.close()

                # 2. Sample shop keeps sample diagnostics & hooks with zero overflow
                cs = browser.new_context(viewport={{"width": width, "height": 844}})
                ps = cs.new_page()
                ps.goto(f"{{BASE}}/?workspace=sample", wait_until="domcontentloaded")
                ps.wait_for_function(
                    "() => window.museModes?.isSampleMode?.() === true && "
                    "(document.querySelector('#metaAdsContainer')?.textContent || '')"
                    ".includes('[sample]')"
                )
                assert "artofsarabjitsingh.com" in ps.locator("#diagnosticsContainer").inner_text()
                assert "Sample competitor ads" in ps.locator("#metaAdsSub").inner_text()
                assert "Storefront Channel Diagnostics" in ps.locator("#diagTitle").inner_text()
                assert not ps.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                cs.close()

            browser.close()
        print(json.dumps({{"status": "ok"}}))
        """
    )

    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
