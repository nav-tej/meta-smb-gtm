"""Saved live results served in demo mode (see src/api/demo.py). No network, no Muse calls."""

from __future__ import annotations

from functools import lru_cache
from itertools import cycle
from pathlib import Path

from src.models.bids import BidRecommendation
from src.models.creative import (
    Creative,
    CreativeSet,
    EditableCreativeBrief,
    EditableCreativeVariant,
    GenerateAdsRequest,
)
from src.models.intel import CompetitorBrief
from src.services.ad_creative import placement_spec

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"
DEMO_PRODUCER = "demo-cache (saved muse-image-1.0 output)"
# Real Muse Image 1.0 outputs committed to data/samples/, served at /samples/
DEMO_IMAGES = (
    "golden_temple_holiday_gift_live.webp",
    "ek_onkar_collector_room_live.webp",
    "kirat_karo_collector_room_live.webp",
    "diptych_ek_onkar_kirat_karo_live.webp",
    "naam_japo_restored_gallery_live.webp",
)


@lru_cache
def demo_competitor_brief() -> CompetitorBrief:
    return CompetitorBrief.model_validate_json(
        (SAMPLES_DIR / "competitor_brief_sikhiart_live.json").read_text()
    )


@lru_cache
def demo_bid_recommendation() -> BidRecommendation:
    return BidRecommendation.model_validate_json((SAMPLES_DIR / "bid_advice_live.json").read_text())


@lru_cache
def _saved_creative_set() -> CreativeSet:
    return CreativeSet.model_validate_json(
        (SAMPLES_DIR / "ad_creative_ek_onkar_live.json").read_text()
    )


def demo_creative_draft(request: GenerateAdsRequest) -> EditableCreativeBrief:
    """Phase 1 draft built from the saved live creative, one variant per requested placement."""
    saved = _saved_creative_set()
    source = saved.creatives[0]
    variants = [
        EditableCreativeVariant(
            variant_id=f"v{i}",
            placement=placement,
            spec=placement_spec(placement),
            target_audience=source.target_audience or "Collectors of Sikh heritage art",
            headline=source.headline,
            primary_text=source.primary_text,
            image_prompt=source.prompt,
        )
        for i, placement in enumerate(request.placements, start=1)
    ]
    return EditableCreativeBrief(
        product_title=request.product.title,
        positioning_hook=saved.positioning_hook or source.headline,
        variants=variants,
        estimated_paid_calls=len(variants),
    )


def demo_creative_set(request: GenerateAdsRequest) -> CreativeSet:
    """Phase 2 / one-shot result: the request's copy paired with saved live images."""
    images = cycle(DEMO_IMAGES)
    if request.brief is not None:
        creatives = [
            Creative(
                placement=v.placement,
                variant_id=v.variant_id,
                target_audience=v.target_audience,
                image_path=f"samples/{next(images)}",
                prompt=v.image_prompt,
                headline=v.headline,
                primary_text=v.primary_text,
                produced_by=DEMO_PRODUCER,
            )
            for v in request.brief.variants
            if v.include
        ]
        hook = request.brief.positioning_hook
    else:
        saved = _saved_creative_set()
        creatives = [
            c.model_copy(
                update={"image_path": f"samples/{next(images)}", "produced_by": DEMO_PRODUCER}
            )
            for c in saved.creatives
        ]
        hook = saved.positioning_hook
    return CreativeSet(
        product_title=request.product.title, creatives=creatives, positioning_hook=hook
    )
