"""Tests for Flow 1: Competitor Intel service (`src.services.competitor_intel`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from src.clients.meta import MetaAPIError, MetaClient
from src.services.competitor_intel import (
    CompetitorBrief,
    CompetitorIntelRequest,
    CompetitorIntelService,
    SitemapEntry,
    SitemapError,
    analyze_competitor,
    crawl,
    derive_signals,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)


async def _public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def _spark_chat_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-intel",
            "object": "chat.completion",
            "created": 1762000000,
            "model": "muse-spark-1.3",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": json.dumps(payload)},
                    "finish_reason": "stop",
                }
            ],
        },
    )


def _sample_brief_llm_payload() -> dict[str, object]:
    return {
        "summary": (
            "This competitor is pushing framed holiday landscape prints and gift guides hard "
            "ahead of Q4, while leaving affordable bundled mini-prints underserved."
        ),
        "product_categories": [
            "Coastal watercolor canvas prints",
            "Framed holiday pine forest art",
            "Botanical wall decor",
        ],
        "pricing_signals": [
            "Premium framed print positioning around $75-$120",
            "Tiered upsell from unframed paper to stretched canvas",
        ],
        "content_strategy_patterns": [
            "Dedicated holiday wall art gift guide blog posts",
            "Medium + subject collection landing pages (/shop/canvas+prints/botanical)",
        ],
        "seo_keywords": [
            "coastal sunset watercolor canvas print",
            "christmas pine forest framed print",
            "holiday wall art gift guide",
        ],
        "new_product_frequency": (
            "Active seasonal push: 3 of 5 tracked URLs were updated in the last 30 days "
            "(~0.31 updates/week over 90 days)."
        ),
        "doubling_down_on": [
            "Holiday and Christmas framed landscape art",
            "Gift-guide editorial content driving Q4 search traffic",
        ],
        "competitor_gaps": [
            "No under-$40 giftable mini-print bundles",
            "No personalized or room-mockup buyer guides for small apartments",
        ],
        "actionable_insights": [
            {
                "title": "Launch a 3-piece Holiday Mini-Print Set under $45",
                "action": (
                    "Bundle three 5x7 botanical or winter watercolor prints as a ready-to-gift "
                    "listing with gift-wrap messaging in the title."
                ),
                "why": (
                    "Competitor focuses on single $75+ framed pieces and has zero entry-price "
                    "holiday bundles."
                ),
                "priority": "high",
            },
            {
                "title": "Publish a 'Holiday Wall Art Under $50' Collection Page",
                "action": (
                    "Group your best-selling seasonal prints into one collection targeting "
                    "'holiday art gift' searchers."
                ),
                "why": (
                    "Competitor recently added a 2026 holiday gift guide to capture Q4 buyers."
                ),
                "priority": "high",
            },
            {
                "title": "Add Medium + Style Keywords to Top Product Titles",
                "action": (
                    "Rename generic print titles to include medium and style, e.g. "
                    "'Coastal Watercolor Canvas Wall Art Print'."
                ),
                "why": (
                    "Every top competitor URL slug pairs art style, subject, and print format."
                ),
                "priority": "medium",
            },
        ],
    }


def test_derive_signals_computes_deterministic_counts() -> None:
    entries = [
        SitemapEntry(
            loc="https://fineartamerica.com/featured/christmas-forest.html",
            lastmod=datetime(2026, 10, 28, tzinfo=UTC),
            title="Christmas Forest Framed Print",
            price_hint="$95.00",
            bucket="products",
        ),
        SitemapEntry(
            loc="https://fineartamerica.com/featured/summer-beach.html",
            lastmod=datetime(2026, 9, 15, tzinfo=UTC),
            title="Summer Beach Canvas",
            price_hint="$65.00",
            bucket="products",
        ),
        SitemapEntry(
            loc="https://fineartamerica.com/blogs/holiday-gift-guide",
            lastmod=datetime(2026, 10, 20, tzinfo=UTC),
            title="Holiday Gift Guide",
            bucket="blogs",
        ),
        SitemapEntry(
            loc="https://fineartamerica.com/featured/older-archive.html",
            lastmod=datetime(2026, 1, 10, tzinfo=UTC),
            title="Older Archive Print",
            bucket="products",
        ),
        SitemapEntry(
            loc="https://fineartamerica.com/pages/about",
            lastmod=None,
            title="About",
            bucket="pages",
        ),
    ]

    signals = derive_signals(
        entries,
        competitor_domain="fineartamerica.com",
        sitemaps_discovered=["https://fineartamerica.com/sitemap.xml"],
        now=FIXED_NOW,
    )

    assert signals.total_urls == 5
    assert signals.bucket_counts == {"products": 3, "blogs": 1, "pages": 1}
    assert signals.recent_30d_count == 2
    assert signals.recent_90d_count == 3
    assert signals.unknown_lastmod_count == 1
    assert signals.publishing_cadence_per_week == round(3 / (90.0 / 7.0), 2)
    assert signals.growing_categories[0] == "products"
    assert signals.detected_price_hints == ["$95.00", "$65.00"]
    assert "christmas" in signals.seasonal_themes
    assert "holiday" in signals.seasonal_themes
    assert "gift" in signals.seasonal_themes


@respx.mock
async def test_analyze_competitor_end_to_end_fineartamerica() -> None:
    sitemap_xml = (FIXTURES / "fineartamerica_sitemap.xml").read_bytes()
    respx.get("https://fineartamerica.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nAllow: /\nSitemap: https://fineartamerica.com/sitemap.xml\n",
        )
    )
    respx.get("https://fineartamerica.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=sitemap_xml)
    )
    pine_url = (
        "https://fineartamerica.com/featured/christmas-pine-forest-framed-print-jane-doe.html"
    )
    respx.get(pine_url).mock(
        return_value=httpx.Response(
            200,
            text=(
                "<html><head>"
                "<title>Christmas Pine Forest Framed Print ($98.00) | FineArtAmerica</title>"
                '<meta property="product:price:amount" content="98.00" />'
                "</head></html>"
            ),
        )
    )
    respx.get(url__regex=r"https://fineartamerica\.com/(featured|shop|blogs)/.*").mock(
        return_value=httpx.Response(200, text="<html><head></head><body></body></html>")
    )
    spark_route = respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=_spark_chat_response(_sample_brief_llm_payload())
    )

    async with httpx.AsyncClient() as http_client:
        meta_client = MetaClient(api_key="test-meta-key", http_client=http_client)
        brief = await analyze_competitor(
            "fineartamerica.com",
            seller_context="Solo watercolor artist selling nature prints on Etsy.",
            http_client=http_client,
            meta_client=meta_client,
            resolver=_public_resolver,
            now=FIXED_NOW,
        )

    assert isinstance(brief, CompetitorBrief)
    assert brief.competitor_domain == "fineartamerica.com"
    assert brief.signals.total_urls == 5
    assert brief.signals.recent_30d_count == 3
    assert "$98.00" in brief.signals.detected_price_hints
    assert brief.batches_analyzed == 1
    assert len(brief.actionable_insights) == 3
    assert brief.product_categories[0] == "Coastal watercolor canvas prints"

    # Verify prompt-injection delimiters wrap competitor URLs + titles sent to Muse Spark
    assert spark_route.call_count == 1
    sent_payload = json.loads(spark_route.calls[0].request.content.decode("utf-8"))
    user_msg = sent_payload["messages"][-1]["content"]
    assert "<untrusted_competitor_data>" in user_msg
    assert "Christmas Pine Forest Framed Print ($98.00) | FineArtAmerica" in user_msg


@respx.mock
async def test_sitemap_index_recursion_and_multi_batch_spark_calls() -> None:
    index_xml = (FIXTURES / "shopify_sitemap_index.xml").read_bytes()
    products_xml = (FIXTURES / "shopify_products.xml").read_bytes()
    blogs_xml = (FIXTURES / "shopify_blogs.xml").read_bytes()

    respx.get("https://modernprintshop.example.com/robots.txt").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://modernprintshop.example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=index_xml)
    )
    respx.get("https://modernprintshop.example.com/sitemap_products_1.xml").mock(
        return_value=httpx.Response(200, content=products_xml)
    )
    respx.get("https://modernprintshop.example.com/sitemap_blogs_1.xml").mock(
        return_value=httpx.Response(200, content=blogs_xml)
    )
    respx.get("https://modernprintshop.example.com/sitemap_pages_1.xml").mock(
        return_value=httpx.Response(404)
    )

    batch_payload = {
        "product_categories": ["Minimalist line art", "Oversized canvas prints"],
        "pricing_signals": ["Under-$50 gift tier mentioned in blog"],
        "content_strategy_patterns": ["Size-selection buying guides"],
        "seo_keywords": ["minimalist line art poster", "christmas art gift ideas under 50"],
        "new_product_frequency": "Multiple October 2026 additions",
        "notable_gaps": ["No custom framing options"],
    }
    # 5 URLs across products (3) + blogs (2) with batch_size=2 -> 3 batch calls + 1 synthesis call
    spark_route = respx.post("https://api.meta.ai/v1/chat/completions").mock(
        side_effect=[
            _spark_chat_response(batch_payload),
            _spark_chat_response(batch_payload),
            _spark_chat_response(batch_payload),
            _spark_chat_response(_sample_brief_llm_payload()),
        ]
    )

    async with httpx.AsyncClient() as http_client:
        meta_client = MetaClient(api_key="test-meta-key", http_client=http_client)
        service = CompetitorIntelService(
            http_client=http_client,
            meta_client=meta_client,
            resolver=_public_resolver,
        )
        brief = await service.analyze(
            CompetitorIntelRequest(
                competitor_url="modernprintshop.example.com",
                seller_context="Shopify poster seller",
                batch_size=2,
                max_batches=5,
                fetch_titles=False,
            )
        )

    assert brief.signals.total_urls == 5
    assert brief.signals.bucket_counts == {"products": 2, "collections": 1, "blogs": 2}
    assert brief.batches_analyzed == 3
    assert spark_route.call_count == 4


@respx.mock
async def test_crawl_shop_url_reads_listing_page_not_sitemaps() -> None:
    etsy_html = (FIXTURES / "etsy_shop_page.html").read_text(encoding="utf-8")
    respx.get("https://www.etsy.com/robots.txt").mock(return_value=httpx.Response(404))
    # A shop URL is a profile page: Etsy's site-wide sitemaps must not be crawled
    sitemap_route = respx.get(url__regex=r"https://www\.etsy\.com/sitemap.*")
    respx.get("https://www.etsy.com/shop/SunlitStudioPrints").mock(
        return_value=httpx.Response(200, text=etsy_html)
    )

    async with httpx.AsyncClient() as http_client:
        entries = await crawl(
            "https://www.etsy.com/shop/SunlitStudioPrints",
            fetch_titles=False,
            http_client=http_client,
            resolver=_public_resolver,
        )

    assert not sitemap_route.called
    assert len(entries) == 2
    assert entries[0].bucket == "listings"
    assert entries[0].price_hint == "$34.00"
    assert "Pressed Wildflower" in (entries[0].title or "")


@respx.mock
async def test_crawl_honors_robots_disallow_and_errors_when_empty() -> None:
    sitemap_xml = (FIXTURES / "shopify_products.xml").read_bytes()
    respx.get("https://modernprintshop.example.com/robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /collections/\n",
        )
    )
    respx.get("https://modernprintshop.example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=sitemap_xml)
    )

    async with httpx.AsyncClient() as http_client:
        entries = await crawl(
            "modernprintshop.example.com",
            fetch_titles=False,
            http_client=http_client,
            resolver=_public_resolver,
        )
    assert all(e.bucket != "collections" for e in entries)
    assert len(entries) == 2

    # Unreachable / empty site raises SitemapError
    respx.get("https://deadshop.example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://deadshop.example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://deadshop.example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://deadshop.example.com/").mock(return_value=httpx.Response(404))

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(SitemapError, match="No competitor URLs could be discovered"):
            await crawl(
                "deadshop.example.com",
                fetch_titles=False,
                http_client=http_client,
                resolver=_public_resolver,
            )


@respx.mock
async def test_analyze_competitor_propagates_meta_api_error() -> None:
    sitemap_xml = (FIXTURES / "shopify_products.xml").read_bytes()
    respx.get("https://modernprintshop.example.com/robots.txt").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://modernprintshop.example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=sitemap_xml)
    )
    respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=httpx.Response(503, json={"error": {"message": "Service overloaded"}})
    )

    async with httpx.AsyncClient() as http_client:
        meta_client = MetaClient(api_key="test-meta-key", http_client=http_client)
        with pytest.raises(MetaAPIError):
            await analyze_competitor(
                "modernprintshop.example.com",
                fetch_titles=False,
                http_client=http_client,
                meta_client=meta_client,
                resolver=_public_resolver,
            )
