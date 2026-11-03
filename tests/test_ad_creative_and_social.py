"""Tests for Hybrid Meta + Open-Weight Krea Ad Creative Studio, Ad Library, and Seller Audit."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from src.clients.ad_library import (
    GRAPH_API_ADS_ARCHIVE_URL,
    AdLibraryError,
    MetaAdLibraryClient,
    load_sample_ad_library_signals,
)
from src.clients.comfyui import ComfyUIClient, ComfyUIError
from src.clients.meta import MetaAPIError, MetaClient
from src.models.creative import GenerateAdsRequest, ProductInfo
from src.models.intel import CompetitorBrief
from src.models.seller import SellerProfile
from src.services.ad_creative import AdCreativeService
from src.services.seller_audit import (
    analyze_social_screenshots,
    audit_seller_footprint,
    compute_seller_diagnostics,
)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SARABJIT_PROFILE_JSON = (SAMPLES_DIR / "sarabjit_singh_profile.json").read_text(encoding="utf-8")
SAMPLE_ADS_JSON = (SAMPLES_DIR / "art_competitor_meta_ads.json").read_text(encoding="utf-8")
# Minimal valid 1x1 PNG bytes
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
FIXED_NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)


def _chat_completion(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-hybrid",
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


def test_sarabjit_singh_seller_diagnostics_from_real_snapshot() -> None:
    profile = SellerProfile.model_validate_json(
        (SAMPLES_DIR / "sarabjit_singh_profile.json").read_text(encoding="utf-8")
    )
    diag = compute_seller_diagnostics(profile)

    assert diag.total_platforms == 7
    assert diag.total_artworks_indexed == 72
    assert diag.has_direct_checkout_gap is True
    assert diag.lowest_pod_print_usd == 14.0
    assert diag.highest_direct_edition_usd == 900.0
    assert any("saatchi_art" in item for item in diag.blocked_or_social_platforms)
    assert any("instagram" in item for item in diag.blocked_or_social_platforms)


def test_sample_ad_library_longevity_and_platform_signals() -> None:
    signals = load_sample_ad_library_signals(
        SAMPLES_DIR / "art_competitor_meta_ads.json",
        now=FIXED_NOW,
    )
    assert signals.total_active_ads == 3
    assert signals.proven_30d_winners_count == 2
    assert signals.platform_counts["instagram"] == 3
    assert signals.platform_counts["facebook"] == 2
    assert signals.top_longevity_ads[0].page_name == "Desi Canvas Co"
    assert signals.top_longevity_ads[0].days_running >= 80


@respx.mock
async def test_meta_ad_library_client_live_query_and_missing_token_error() -> None:
    sample_raw = json.loads(SAMPLE_ADS_JSON)
    respx.get(GRAPH_API_ADS_ARCHIVE_URL).mock(return_value=httpx.Response(200, json=sample_raw))

    async with httpx.AsyncClient() as http_client:
        client = MetaAdLibraryClient(access_token="  graph-token  ", http_client=http_client)
        signals = await client.search_active_ads("Golden Temple canvas", now=FIXED_NOW)
        assert signals.proven_30d_winners_count == 2

        empty_client = MetaAdLibraryClient(access_token="", http_client=http_client)
        with pytest.raises(AdLibraryError, match="META_ADS_ACCESS_TOKEN"):
            await empty_client.search_active_ads("Sikh art")


@respx.mock
async def test_hybrid_muse_plus_open_weight_flux_krea_creative_pipeline(
    competitor_brief: CompetitorBrief, tmp_path: Path
) -> None:
    b64_png = base64.b64encode(TINY_PNG).decode("ascii")

    # 1. SAM 3.1 segmentation endpoint
    sam_route = respx.post("https://api.meta.ai/v1/images/segmentations").mock(
        return_value=httpx.Response(200, json={"mask_b64": b64_png})
    )

    # 2. Muse Spark 1.3 creative brief endpoint
    brief_llm_payload = {
        "positioning_hook": "Museum-exhibited Sikh heritage giclee with 18k gold ink",
        "preserve_product_note": "Keep Ek Onkar brushwork 100% untouched via SAM 3.1 mask.",
        "angles": [
            {
                "placement": "instagram_feed",
                "scene_prompt": "Warm sunlit California living room wall above a walnut credenza",
                "headline": "Ek Onkar — Hand-Signed 18k Gold Giclee ($75)",
                "primary_text": "Exhibited at Triton Museum & Kala Sangam. Free US shipping.",
                "angle_rationale": "Bridges $18 mass posters vs $900 gallery pieces.",
            }
        ],
    }
    respx.post("https://api.meta.ai/v1/chat/completions").mock(
        return_value=_chat_completion(brief_llm_payload)
    )

    # 3. Muse Image 1.0 base creative generation endpoint
    muse_img_route = respx.post("https://api.meta.ai/v1/images/generations").mock(
        return_value=httpx.Response(200, json={"data": [{"b64_json": b64_png}]})
    )

    # 4. ComfyUI FLUX.1-Krea-dev open-weight variant server endpoints
    respx.get("http://127.0.0.1:8188/system_stats").mock(
        return_value=httpx.Response(200, json={"system": {"os": "darwin"}})
    )
    respx.post("http://127.0.0.1:8188/upload/image").mock(
        side_effect=[
            httpx.Response(200, json={"name": "ek_onkar_input.png"}),
            httpx.Response(200, json={"name": "ek_onkar_sam3_mask.png"}),
        ]
    )
    comfy_prompt_route = respx.post("http://127.0.0.1:8188/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "krea-job-001"})
    )
    respx.get("http://127.0.0.1:8188/history/krea-job-001").mock(
        return_value=httpx.Response(
            200,
            json={
                "krea-job-001": {
                    "outputs": {
                        "11": {
                            "images": [
                                {
                                    "filename": "meta_smb_krea_scene_0001.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            },
        )
    )
    respx.get("http://127.0.0.1:8188/view").mock(return_value=httpx.Response(200, content=TINY_PNG))

    async with httpx.AsyncClient() as http_client:
        meta_client = MetaClient(api_key="test-meta-key", http_client=http_client)
        comfy_client = ComfyUIClient(
            base_url="http://127.0.0.1:8188",
            http_client=http_client,
            poll_interval_seconds=0.0,
        )
        service = AdCreativeService(
            meta_client=meta_client,
            comfy_client=comfy_client,
            http_client=http_client,
            output_dir=tmp_path,
        )
        result = await service.generate(
            GenerateAdsRequest(
                product=ProductInfo(
                    title="Ek Onkar (Guru Nanak 550th Series)",
                    description="24x24 acrylic on canvas; 18k gold embellished signed giclee.",
                    image_base64=b64_png,
                    price="$75",
                    brand_notes="Art of Sarabjit Singh — museum-exhibited Bay Area Sikh artist.",
                ),
                competitor_brief=competitor_brief,
                placements=["instagram_feed"],
                variants_per_placement=2,
                use_comfyui=True,
                comfyui_workflow="flux_krea_scene_relight",
            )
        )

    assert sam_route.called
    assert muse_img_route.called
    assert comfy_prompt_route.called
    assert result.mask_path is not None and result.mask_path.endswith(".png")
    assert len(result.creatives) == 2
    assert result.creatives[0].produced_by == "muse-image-1.0"
    assert result.creatives[1].produced_by == "comfyui:flux_krea_scene_relight"

    # Verify ComfyUI graph received FLUX.1-Krea-dev checkpoint + 4:5 IG dimensions (1080x1350)
    submitted_graph = json.loads(comfy_prompt_route.calls[0].request.content)["prompt"]
    assert submitted_graph["3"]["inputs"]["unet_name"] == "flux1-krea-dev.safetensors"
    assert submitted_graph["7"]["inputs"]["width"] == 1080
    assert submitted_graph["7"]["inputs"]["height"] == 1350


@respx.mock
async def test_audit_seller_footprint_and_screenshot_vision(
    competitor_brief: CompetitorBrief,
) -> None:
    profile = SellerProfile.model_validate_json(SARABJIT_PROFILE_JSON)
    audit_llm = {
        "executive_summary": (
            "Sarabjit has museum-level credibility (UCLA Fowler, de Young, Stanford) and $75-$150 "
            "18k-gold signed giclees on artofsarabjitsingh.com, but buyers hit a manual contact "
            "form while FineArtAmerica anchors her art next to $28 phone cases."
        ),
        "website_seo_and_conversion_fixes": [
            {
                "title": "Add Stripe Payment Links to Guru Nanak & Goddess Series Pages",
                "action": (
                    "Add 1-click Buy buttons for the $75 (12x12) and $125 (24x24) signed "
                    "giclees on gurus.html."
                ),
                "why": "artofsarabjitsingh.com currently requires emailing a contact form to buy.",
                "priority": "high",
            }
        ],
        "marketplace_and_pricing_fixes": [
            {
                "title": "Disable Novelty Merch on Flagship Heritage Works on FineArtAmerica",
                "action": (
                    "Turn off shower curtains, tote bags, and phone cases on Golden Temple "
                    "and Mai Bhago."
                ),
                "why": "Novelty items undercut $75-$900 collector giclee positioning.",
                "priority": "high",
            }
        ],
        "instagram_and_facebook_sales_plays": [
            {
                "title": "Run a Gurpurab Collector Reel Featuring 18k Gold Ink Closeups",
                "action": (
                    "Post a 15s Reel of Sarabjit hand-signing Ek Onkar paired with a "
                    "FLUX-Krea living-room wall mockup."
                ),
                "why": "Competitor Golden Temple canvas ads have run 80+ days profitably on IG/FB.",
                "priority": "high",
            }
        ],
    }
    vision_llm = {
        "platform_detected": "instagram",
        "visual_merchandising_hooks": ["Flat unframed canvas crop without room scale"],
        "pricing_and_offer_signals": ["No price or link-in-bio tier mentioned in caption"],
        "copy_and_seo_keywords": ["Sikh art", "Bay Area artist"],
        "conversion_friction_or_gaps": ["Collectors cannot judge 24x24 scale above furniture"],
        "actionable_insights": [
            {
                "title": "Add Carousel Slide 2 Showing Painting Hung Above a Sofa",
                "action": "Use Ad Creative Studio's SAM 3.1 + FLUX-Krea room mockup as Slide 2.",
                "why": "Top 30d+ IG art ads show room scale immediately.",
                "priority": "high",
            }
        ],
    }

    respx.post("https://api.meta.ai/v1/chat/completions").mock(
        side_effect=[_chat_completion(audit_llm), _chat_completion(vision_llm)]
    )

    async with httpx.AsyncClient() as http_client:
        meta_client = MetaClient(api_key="test-key", http_client=http_client)
        audit = await audit_seller_footprint(
            profile,
            competitor_brief=competitor_brief,
            meta_client=meta_client,
        )
        vision = await analyze_social_screenshots(
            [TINY_PNG],
            context="@artofsarabjitsingh Instagram grid screenshot",
            meta_client=meta_client,
        )

    assert audit.diagnostics.has_direct_checkout_gap is True
    assert len(audit.website_seo_and_conversion_fixes) == 1
    assert vision.platform_detected == "instagram"


async def test_comfyui_rejects_path_traversal_and_invalid_image_rejected() -> None:
    comfy = ComfyUIClient(base_url="http://127.0.0.1:8188")
    with pytest.raises(ComfyUIError, match="Invalid workflow name"):
        await comfy.run_workflow("../etc/passwd", {})
    await comfy.aclose()

    client = MetaClient(api_key="test-key")
    with pytest.raises(MetaAPIError, match="Unsupported image format"):
        await client.segment(b"not-an-image")
    await client.aclose()
