"""End-to-end runnable demo & smoke test for 'Art of Sarabjit Singh'.

Exercises the full closed-loop growth copilot across:
  1. Own-site + Multi-Marketplace Audit (`artofsarabjitsingh.com`, FineArtAmerica, Saatchi, FB, IG)
  2. Meta Ad Library IG/FB Competitor Longevity Signals + Sitemap Competitor Brief
  3. Hybrid Meta (`SAM 3.1` + `Muse Spark 1.3` + `Muse Image 1.0`) + Open-Weight (`ComfyUI`
     `FLUX.1-Krea-dev`) Ad Creative Studio preserving 100% of Sarabjit's original brushwork
  4. Deterministic Python + `Muse Spark 1.3` Bid Advisor for Gurpurab / Q4 collector ads

Usage:
  .venv/bin/python scripts/demo_sarabjit_singh.py --dry-run
  .venv/bin/python scripts/demo_sarabjit_singh.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.ad_library import load_sample_ad_library_signals  # noqa: E402
from src.clients.comfyui import ComfyUIClient  # noqa: E402
from src.clients.meta import MetaClient  # noqa: E402
from src.models.bids import (  # noqa: E402
    AdSetDailyPerformance,
    BidAdviceRequest,
    CampaignPerformance,
)
from src.models.creative import GenerateAdsRequest, ProductInfo  # noqa: E402
from src.models.intel import CompetitorBrief  # noqa: E402
from src.models.seller import SellerProfile  # noqa: E402
from src.services.ad_creative import AdCreativeService  # noqa: E402
from src.services.bid_advisor import BidAdvisorService  # noqa: E402
from src.services.competitor_intel import analyze_competitor  # noqa: E402
from src.services.seller_audit import audit_seller_footprint  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
FIXTURES = ROOT / "tests" / "fixtures"
DEMO_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _build_sarabjit_campaign() -> CampaignPerformance:
    """Sample 7-day Meta Ads Manager campaign for Art of Sarabjit Singh."""
    start = date(2026, 10, 26)
    rows: list[AdSetDailyPerformance] = []
    for d in range(7):
        day = start + timedelta(days=d)
        rows.append(
            AdSetDailyPerformance(
                day=day,
                campaign_name="Gurpurab & Holiday Signed Giclees",
                ad_set_name="IG+FB Warm Engagers - Guru Nanak 550th Series",
                impressions=2400,
                clicks=78,
                conversions=2,
                spend=22.0,
                conversion_value=200.0,
                frequency=1.9,
                daily_budget=22.0,
            )
        )
        rows.append(
            AdSetDailyPerformance(
                day=day,
                campaign_name="Gurpurab & Holiday Signed Giclees",
                ad_set_name="Broad Collectors - US/CA/UK South Asian Art",
                impressions=6800,
                clicks=110,
                conversions=1,
                spend=35.0,
                conversion_value=125.0,
                frequency=1.4,
                daily_budget=40.0,
            )
        )
        rows.append(
            AdSetDailyPerformance(
                day=day,
                campaign_name="Gurpurab & Holiday Signed Giclees",
                ad_set_name="Generic Home Decor Interest - Unframed Prints",
                impressions=5200,
                clicks=max(28, 85 - d * 9),
                conversions=0 if d >= 2 else 1,
                spend=28.0,
                conversion_value=0.0 if d >= 2 else 42.0,
                frequency=1.8 + 0.3 * d,
                daily_budget=30.0,
            )
        )
    return CampaignPerformance(account_name="Art of Sarabjit Singh", currency="USD", rows=rows)


def _mock_transport(spark_bid_template: dict[str, object]) -> httpx.MockTransport:
    """Deterministic offline transport simulating Meta Model API + ComfyUI FLUX.1-Krea-dev."""
    audit_json = {
        "executive_summary": (
            "Sarabjit Singh brings rare museum credibility (UCLA Fowler Museum, de Young Museum, "
            "Stanford) and hand-signed 18k-gold-embellished giclees ($75-$150), yet "
            "artofsarabjitsingh.com forces buyers into an email contact form while FineArtAmerica "
            "displays her heritage paintings on $28 phone cases and shower curtains."
        ),
        "website_seo_and_conversion_fixes": [
            {
                "title": "Add 1-Click Stripe Checkout Buttons on gurus.html & goddess-art.html",
                "action": (
                    "Place direct Buy buttons for the $75 (12x12) and $125 (24x24) signed "
                    "18k-gold giclees right beneath Ek Onkar and Mai Bhago."
                ),
                "why": (
                    "artofsarabjitsingh.com currently relies on a manual contact form, "
                    "losing impulse social traffic."
                ),
                "priority": "high",
            },
            {
                "title": "Rewrite Generic Weebly Page Titles with Collector SEO Keywords",
                "action": (
                    "Update page <title> on gurus.html from 'Gurus' to 'Guru Nanak Dev Sikh "
                    "Heritage Signed Giclee Prints | Art of Sarabjit Singh'."
                ),
                "why": "Competitors rank on 'Golden Temple canvas' and 'Sikh wall art' slugs.",
                "priority": "high",
            },
        ],
        "marketplace_and_pricing_fixes": [
            {
                "title": "Turn Off Novelty Merch on Heritage & Goddess Paintings on FAA/Pixels",
                "action": (
                    "Disable shower curtains, tote bags, and phone cases on Golden Temple, "
                    "Banda Singh Bahadur, and Mai Bhago."
                ),
                "why": "Low-ticket novelty items dilute $75-$900 limited-edition positioning.",
                "priority": "high",
            },
            {
                "title": "Fill Missing Series Tags & Original Prices Across 72 Indexed Works",
                "action": (
                    "Group uncategorized FAA paintings into 'Golden Temple', 'Goddess', and "
                    "'Punjab Heritage' collections and list original availability."
                ),
                "why": (
                    "71 of 72 indexed listings lack original canvas pricing, hiding $3,000 "
                    "original sales potential."
                ),
                "priority": "medium",
            },
        ],
        "instagram_and_facebook_sales_plays": [
            {
                "title": "Launch a Gurpurab 2-Slide IG/FB Ad (Artist Signing + Krea Room Mockup)",
                "action": (
                    "Pair a closeup of 18k gold ink on Ek Onkar with the SAM 3.1 + FLUX.1-Krea "
                    "living-room wall mockup."
                ),
                "why": (
                    "Meta Ad Library shows Golden Temple ready-to-hang room ads running 80+ "
                    "days profitably on IG & FB."
                ),
                "priority": "high",
            }
        ],
    }

    creative_brief_json = {
        "positioning_hook": "Museum-exhibited Bay Area Sikh artist — signed 18k gold ink giclee",
        "preserve_product_note": (
            "SAM 3.1 mask locks 100% of Sarabjit Singh's original Ek Onkar acrylic brushwork."
        ),
        "angles": [
            {
                "placement": "instagram_feed",
                "scene_prompt": (
                    "Sunlit modern California living room wall above a warm walnut console, "
                    "soft museum track lighting, untouched framed canvas centerpiece"
                ),
                "headline": "Ek Onkar — Hand-Signed 18k Gold Edition ($75)",
                "primary_text": (
                    "Exhibited at Triton Museum & Bradford UK. Hand-embellished with 18k gold "
                    "ink by Bay Area artist Sarabjit Singh. Edition of 100, free US shipping."
                ),
                "angle_rationale": (
                    "Beats $129 mass-printed competitor canvases with authentic signed "
                    "museum provenance at $75-$125."
                ),
            },
            {
                "placement": "reels_cover",
                "scene_prompt": (
                    "Warm evening home sanctuary glow with brass accents and natural linen "
                    "textures surrounding the untouched painting"
                ),
                "headline": "Meaningful Gurpurab & Housewarming Art",
                "primary_text": (
                    "Every brushstroke tells a story—never mass-produced decor. "
                    "Signed Certificate of Authenticity included."
                ),
                "angle_rationale": "Targets Q4 Gurpurab, Diwali, and wedding gifting gap.",
            },
        ],
    }

    bid_json = {
        "performance_summary": (
            "Your Guru Nanak 550th warm-engager ad set earns $9.09 ROAS and hits its $22/day cap "
            "daily, while the generic unframed decor ad set is fatiguing with falling CTR."
        ),
        "trend_analysis": [
            "Generic Home Decor Interest - Unframed Prints: CTR fell sharply as frequency rose.",
            "IG+FB Warm Engagers - Guru Nanak 550th Series: hits 100% daily budget at best ROAS.",
        ],
        "competitive_context": [
            "Competitors spend heavily on $129 mass-printed canvases; your $75-$125 hand-signed "
            "18k-gold giclees win on museum provenance."
        ],
        "bid_adjustments": [
            {
                "ad_set_name": "IG+FB Warm Engagers - Guru Nanak 550th Series",
                "action": "increase",
                "bid_strategy": "lowest_cost",
                "triggering_metric": "spend_pacing",
                "reasoning": "Spending 100% of its $22/day cap while returning 9.09x ROAS.",
                "expected_impact": "Captures more Gurpurab collector sales before edition caps.",
            },
            {
                "ad_set_name": "Generic Home Decor Interest - Unframed Prints",
                "action": "decrease",
                "bid_strategy": "cost_cap",
                "triggering_metric": "ctr_trend",
                "reasoning": "Click-through rate fell in half while frequency climbed above 3.5.",
                "expected_impact": "Stops wasted spend on cold decor browsers.",
            },
        ],
        "budget_shifts": [
            {
                "from_ad_set": "Generic Home Decor Interest - Unframed Prints",
                "to_ad_set": "IG+FB Warm Engagers - Guru Nanak 550th Series",
                "shift_percent": 30,
                "triggering_metric": "roas",
                "reasoning": (
                    "Move 30% of the fatiguing decor ad set into the budget-capped signed "
                    "giclee winner."
                ),
            }
        ],
        "pause_candidates": [
            {
                "ad_set_name": "Generic Home Decor Interest - Unframed Prints",
                "triggering_metric": "ctr_trend",
                "reasoning": "Cold home-decor browsers aren't converting on unframed prints.",
                "alternative": (
                    "Swap in the new FLUX.1-Krea room-mockup creative pointing to $75 signed "
                    "giclees before pausing."
                ),
            }
        ],
        "audience_suggestions": [
            {
                "audience": "South Asian diaspora & museum art patrons (US, Canada, UK)",
                "competitor_gap": "No museum-exhibited hand-signed 18k-gold limited editions",
                "rationale": "Sarabjit's UCLA Fowler & de Young Museum shows convert collectors.",
                "how_to_test": (
                    "Create an IG+FB Reels ad set featuring Ek Onkar at $75 with free US shipping."
                ),
            }
        ],
        "next_steps": [
            "Shift 30% ($8.40/day) from Generic Home Decor into IG+FB Warm Engagers.",
            "Upload the new SAM 3.1 + FLUX.1-Krea Ek Onkar room mockup to Instagram Feed & Reels.",
            "Add 1-click Stripe checkout buttons on artofsarabjitsingh.com/gurus.html.",
        ],
    }

    upload_counter = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_counter
        url = str(request.url)
        if url.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            sys_text = body["messages"][0]["content"]
            if "website_seo_and_conversion_fixes" in sys_text:
                chosen: object = audit_json
            elif "positioning_hook" in sys_text:
                chosen = creative_brief_json
            else:
                chosen = bid_json
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-demo",
                    "object": "chat.completion",
                    "created": 1762000000,
                    "model": "muse-spark-1.3",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": json.dumps(chosen)},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        if url.endswith("/images/segmentations"):
            return httpx.Response(200, json={"mask_b64": DEMO_PNG_B64})
        if url.endswith("/images/generations"):
            return httpx.Response(200, json={"data": [{"b64_json": DEMO_PNG_B64}]})
        if url.endswith("/system_stats"):
            return httpx.Response(200, json={"system": {"os": "darwin"}})
        if url.endswith("/upload/image"):
            upload_counter += 1
            return httpx.Response(200, json={"name": f"uploaded_{upload_counter}.png"})
        if url.endswith("/prompt"):
            return httpx.Response(200, json={"prompt_id": "krea-demo-prompt"})
        if "/history/" in url:
            return httpx.Response(
                200,
                json={
                    "krea-demo-prompt": {
                        "outputs": {
                            "11": {
                                "images": [
                                    {
                                        "filename": "krea_out.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        if "/view" in url:
            return httpx.Response(200, content=base64.b64decode(DEMO_PNG_B64))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def run_demo(
    *,
    live: bool,
    profile: SellerProfile,
    competitor_brief_fixture: CompetitorBrief,
    spark_bid_template: dict[str, object],
) -> None:
    social_signals = load_sample_ad_library_signals(
        SAMPLES / "art_competitor_meta_ads.json",
        now=datetime(2026, 11, 3, tzinfo=UTC),
    )

    if live:
        http_client = httpx.AsyncClient(timeout=60.0)
        meta_client = MetaClient(http_client=http_client)
        comfy_client = ComfyUIClient(http_client=http_client)
        competitor_brief = await analyze_competitor(
            "https://www.artofsarabjitsingh.com/",
            seller_context=profile.to_seller_context(),
            http_client=http_client,
            meta_client=meta_client,
        )
    else:
        http_client = httpx.AsyncClient(transport=_mock_transport(spark_bid_template))
        meta_client = MetaClient(api_key="dry-run-key", http_client=http_client)
        comfy_client = ComfyUIClient(
            base_url="http://127.0.0.1:8188",
            http_client=http_client,
            poll_interval_seconds=0.0,
        )
        competitor_brief = competitor_brief_fixture.model_copy(deep=True)
        competitor_brief.signals.social_signals = social_signals

    try:
        print(f"\n=== 1. MULTI-CHANNEL AUDIT: {profile.business_name} ({profile.location}) ===")
        audit = await audit_seller_footprint(
            profile,
            competitor_brief=competitor_brief,
            social_signals=social_signals,
            meta_client=meta_client,
        )
        print(f"Summary: {audit.executive_summary}")
        print(
            f"Diagnostics: {audit.diagnostics.total_artworks_indexed} works indexed | "
            f"POD from ${audit.diagnostics.lowest_pod_print_usd} vs Direct Signed Editions up to "
            f"${audit.diagnostics.highest_direct_edition_usd} | "
            f"Website checkout gap: {audit.diagnostics.has_direct_checkout_gap}"
        )
        print(
            f"IG/FB Ad Library Signals: {social_signals.total_active_ads} active competitor ads "
            f"({social_signals.proven_30d_winners_count} running 30+ days on IG/FB)"
        )
        for fix in (
            audit.website_seo_and_conversion_fixes
            + audit.marketplace_and_pricing_fixes
            + audit.instagram_and_facebook_sales_plays
        ):
            print(f"  - [{fix.priority.upper()}] {fix.title}: {fix.action}")

        print("\n=== 2. AD CREATIVE STUDIO: SAM 3.1 + Muse Spark + Muse Image + FLUX.1-Krea ===")
        creative_service = AdCreativeService(
            meta_client=meta_client,
            comfy_client=comfy_client,
            http_client=http_client,
            output_dir=ROOT / "outputs" / "demo_sarabjit",
        )
        creative_set = await creative_service.generate(
            GenerateAdsRequest(
                product=ProductInfo(
                    title="Ek Onkar — Guru Nanak 550th Anniversary Signed 18k Gold Giclee",
                    description=profile.series[0].summary,
                    image_base64=DEMO_PNG_B64,
                    price="$75 (12x12) / $125 (24x24)",
                    brand_notes=profile.to_seller_context(),
                ),
                competitor_brief=competitor_brief,
                placements=["instagram_feed", "reels_cover"],
                variants_per_placement=2,
                use_comfyui=True,
                comfyui_workflow="flux_krea_scene_relight",
            )
        )
        print(f"Positioning Hook: {creative_set.positioning_hook}")
        print(f"SAM 3.1 Mask Saved: {creative_set.mask_path}")
        for c in creative_set.creatives:
            print(f"  - [{c.placement}] ({c.produced_by}) '{c.headline}' -> {c.image_path}")

        print("\n=== 3. BID ADVISOR: Deterministic Metrics + Muse Spark 1.3 ===")
        bid_service = BidAdvisorService(meta_client=meta_client)
        advice = await bid_service.advise(
            BidAdviceRequest(
                campaign=_build_sarabjit_campaign(),
                competitor_brief=competitor_brief,
                seller_goal=(
                    "Drive direct sales of $75-$150 signed 18k-gold giclees on "
                    "artofsarabjitsingh.com ahead of Gurpurab and Q4 holidays."
                ),
            )
        )
        print(f"Summary: {advice.performance_summary}")
        for realloc in advice.budget_reallocations:
            print(
                f"  - Shift ${realloc.daily_amount:.2f}/day ({realloc.shift_percent}%) "
                f"from '{realloc.from_ad_set}' -> '{realloc.to_ad_set}'"
            )
        for step in advice.next_steps:
            print(f"  - Next Step: {step}")
    finally:
        await http_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Art of Sarabjit Singh E2E Growth Demo.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True, help="Offline mock run")
    group.add_argument("--live", action="store_true", help="Hit live api.meta.ai/v1 & ComfyUI")
    args = parser.parse_args()

    profile = SellerProfile.model_validate_json(
        (SAMPLES / "sarabjit_singh_profile.json").read_text(encoding="utf-8")
    )
    competitor_brief_fixture = CompetitorBrief.model_validate_json(
        (FIXTURES / "competitor_brief.json").read_text(encoding="utf-8")
    )
    spark_bid_template = json.loads(
        (FIXTURES / "muse_spark_bid_response.json").read_text(encoding="utf-8")
    )
    asyncio.run(
        run_demo(
            live=bool(args.live),
            profile=profile,
            competitor_brief_fixture=competitor_brief_fixture,
            spark_bid_template=spark_bid_template,
        )
    )


if __name__ == "__main__":
    main()
