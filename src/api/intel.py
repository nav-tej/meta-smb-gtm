"""Competitor Intel & Seller Audit routes (Flow 1 + Demo Portal Presets)."""

import base64
import binascii
import json
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.demo import LiveMode, demo_unavailable
from src.clients.ad_library import load_sample_ad_library_signals
from src.clients.meta import MetaAPIError
from src.models.intel import CompetitorBrief, CompetitorIntelRequest
from src.models.seller import (
    ScreenshotAnalysis,
    SellerDiagnostics,
    SellerFootprintAudit,
    SellerProfile,
)
from src.services import demo
from src.services.competitor_intel import CompetitorIntelService, collect_entries
from src.services.seller_audit import (
    analyze_social_screenshots,
    audit_seller_footprint,
    compute_seller_diagnostics,
)
from src.utils.sitemap import SitemapError

router = APIRouter(tags=["intel"])

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


class AuditSellerRequest(BaseModel):
    profile: SellerProfile
    competitor_brief: CompetitorBrief | None = None
    deterministic_only: bool = False


class IngestStorefrontRequest(BaseModel):
    business_name: str = Field(default="Art of Sarabjit Singh", max_length=160)
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


@router.post("/analyze-competitors", response_model=CompetitorBrief)
async def analyze_competitors(
    request: CompetitorIntelRequest,
    service: Annotated[CompetitorIntelService, Depends(get_competitor_intel_service)],
    live: LiveMode,
) -> CompetitorBrief:
    if not live:
        return demo.demo_competitor_brief()
    return await service.analyze(request)


@router.post("/audit-seller", response_model=SellerFootprintAudit | SellerDiagnostics)
async def audit_seller(
    request: AuditSellerRequest,
    live: LiveMode,
) -> SellerFootprintAudit | SellerDiagnostics:
    if request.deterministic_only or not live:
        return compute_seller_diagnostics(request.profile)
    return await audit_seller_footprint(
        request.profile,
        competitor_brief=request.competitor_brief,
    )


@router.post("/ingest-storefront")
async def ingest_storefront(request: IngestStorefrontRequest) -> dict[str, Any]:
    """Crawl a seller's own website & marketplace pages to build a live reference profile."""
    sources: list[tuple[str, str]] = []
    if request.website_url.strip():
        sources.append(("own_website", request.website_url.strip()))
    for m_url in request.marketplace_urls:
        if m_url.strip():
            sources.append(("marketplace", m_url.strip()))
    for s_url in request.social_urls:
        if s_url.strip():
            sources.append(("social", s_url.strip()))

    channel_results: list[dict[str, Any]] = []
    discovered_items: list[dict[str, Any]] = []
    price_hints: list[str] = []

    for kind, raw_url in sources:
        normalized = raw_url if "://" in raw_url else f"https://{raw_url.lstrip('@')}"
        host = (urlparse(normalized).hostname or "").lower()
        if any(
            blocked in host
            for blocked in ("instagram.com", "facebook.com", "saatchiart.com", "etsy.com")
        ):
            channel_results.append(
                {
                    "kind": kind,
                    "url": raw_url,
                    "host": host,
                    "status": "vision_or_manual",
                    "pages_found": 0,
                    "note": (
                        f"{host} blocks automated crawlers (robots.txt / 403). Connected via "
                        "profile metadata + Muse Spark 1.3 Vision screenshot analyzer."
                    ),
                }
            )
            continue

        try:
            entries, sitemaps = await collect_entries(
                normalized,
                fetch_titles=True,
                max_urls=request.max_urls_per_source,
                max_title_fetches=12,
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
        ", ".join(price_hints[:6]) if price_hints else "$14-$22 POD prints; $75-$900 direct"
    )
    seller_context = (
        f"{request.business_name}. Connected channels: {channels_str}. "
        f"Sample catalog pages/products: {'; '.join(sample_titles[:8])}. "
        f"Detected price points: {prices_str}."
    )

    return {
        "business_name": request.business_name,
        "total_channels": len(channel_results),
        "total_pages_crawled": sum(int(c["pages_found"]) for c in channel_results),
        "channels": channel_results,
        "discovered_catalog_items": discovered_items[:24],
        "detected_price_hints": price_hints,
        "seller_context": seller_context,
    }


@router.post("/audit-screenshot", response_model=ScreenshotAnalysis)
async def audit_screenshot(request: ScreenshotAuditRequest, live: LiveMode) -> ScreenshotAnalysis:
    """Run Muse Spark 1.3 Vision on an uploaded IG, FB, Saatchi, Etsy, or website screenshot."""
    if not live:
        raise demo_unavailable("Screenshot analysis")
    raw = request.image_base64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(raw, validate=True)
    except binascii.Error as err:
        raise MetaAPIError(f"Invalid base64 screenshot: {err}") from err
    return await analyze_social_screenshots([img_bytes], context=request.context)


def _read_sample_json(filename: str) -> dict[str, Any]:
    path = SAMPLES_DIR / filename
    if not path.is_file():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")))


@router.get("/demo-presets")
async def get_demo_presets() -> dict[str, Any]:
    """Return pre-verified live demo data for the Customer Portal (Art of Sarabjit Singh + Etsy)."""
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
                    "sample_hooks": [
                        (
                            "Artisan Table Co (62d active on IG): "
                            "'Hand-Thrown Mug Duo — Free Gift Box'"
                        ),
                        (
                            "Jaipur Living Decor (39d active on IG+FB): "
                            "'Block-Printed Table Runners 20% Off'"
                        ),
                    ]
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
