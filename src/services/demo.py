"""Saved live results served in demo mode (see src/api/demo.py). No network, no Muse calls."""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from itertools import cycle
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

from src.models.bids import BidRecommendation
from src.models.creative import (
    Creative,
    CreativeSet,
    EditableCreativeBrief,
    EditableCreativeVariant,
    GenerateAdsRequest,
)
from src.models.intel import CitedInsight, CompetitorBrief, CompetitorSignals
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


# Saved public snapshots for the suggested competitors (captured Nov 3 by the crawler).
COMPETITOR_SNAPSHOTS = {
    "gurinderpreet-kaur": (
        "Gurinderpreet Kaur",
        "Fine Art America",
        "competitor_gurinderpreet_kaur.json",
    ),
    "manjot-singh-sachdeva": (
        "Manjot Singh Sachdeva",
        "Fine Art America / Pixels",
        "competitor_manjot_singh_sachdeva.json",
    ),
    "gurdishpannu": ("Gurdish Pannu", "Saatchi Art", "competitor_gurdish_pannu.json"),
}
HER_PRINT_RANGE = (14.0, 22.0)
_STOPWORDS = {
    "art",
    "for",
    "sale",
    "fine",
    "america",
    "the",
    "and",
    "of",
    "by",
    "print",
    "prints",
    "canvas",
    "framed",
    "poster",
    "photograph",
    "painting",
    "kaur",
    "singh",
    "gurinder",
    "preet",
    "manjot",
    "sachdeva",
    "gurdish",
    "pannu",
    "saatchi",
    "with",
    "from",
}


def _snapshot_for(url: str) -> tuple[str, str, dict] | None:
    path = urlparse(url if "://" in url else f"https://{url}").path.lower() + " " + url.lower()
    for slug, (name, platform, filename) in COMPETITOR_SNAPSHOTS.items():
        if slug in path:
            return name, platform, json.loads((SAMPLES_DIR / filename).read_text())
    return None


def _usd(value: object) -> float | None:
    text = str(value or "")
    if not text.startswith("$"):
        return None
    try:
        return float(re.sub(r"[^0-9.]", "", text.split("-")[0]))
    except ValueError:
        return None


def snapshot_competitor_brief(url: str) -> CompetitorBrief | None:
    """Deterministic brief from a saved competitor snapshot. No model call, no network."""
    found = _snapshot_for(url)
    if found is None:
        return None
    name, platform, snap = found
    entries = snap.get("entries", [])
    buckets = Counter(e.get("bucket", "other") for e in entries)
    prices = sorted(p for p in (_usd(e.get("price_hint")) for e in entries) if p is not None)
    titles = [
        str(e.get("title", "")).split("|")[0].strip()
        for e in entries
        if e.get("bucket") == "products"
    ]
    words = Counter(
        w for t in titles for w in re.findall(r"[A-Za-z]{4,}", t.lower()) if w not in _STOPWORDS
    )
    subjects = [w.title() for w, n in words.most_common(8) if n >= 2][:5]
    captured = snap.get("captured", "Nov 3")
    pricing, insights, gaps = [], [], []
    if prices:
        mid = median(prices)
        pricing = [
            f"Listed prices ${prices[0]:.2f}–${prices[-1]:.2f}",
            f"Median ${mid:.2f} across {len(prices)} priced listings",
        ]
        if mid > HER_PRINT_RANGE[1]:
            insights.append(
                CitedInsight(
                    title="Lead with your lower entry price",
                    action=(
                        f"Their median listing is ${mid:.2f}; make your $14–$22 Pixels prints "
                        "the easy first purchase in your next post."
                    ),
                    why=(
                        f"{len(prices)} of their listings are priced, "
                        "with a median above your print range."
                    ),
                    priority="high",
                )
            )
        else:
            insights.append(
                CitedInsight(
                    title="Compete on story, not price",
                    action=(
                        "Your print prices overlap theirs, so lead with the meaning behind "
                        "one painting rather than a discount."
                    ),
                    why=f"Their median listing (${mid:.2f}) sits inside your $14–$22 print range.",
                    priority="high",
                )
            )
    else:
        pricing = ["No USD prices in the snapshot (originals or non-USD listings)."]
    if subjects:
        insights.append(
            CitedInsight(
                title=f"Watch their focus: {', '.join(subjects[:3])}",
                action=(
                    "Check that your work on similar subjects is titled and tagged so buyers "
                    "searching these words find it."
                ),
                why=(
                    f"These are the most frequent words across {len(titles)} product titles "
                    "in the snapshot."
                ),
                priority="medium",
            )
        )
    if buckets.get("collections", 0) > 0:
        gaps.append(f"{buckets['collections']} collection pages: they group products by type.")
    insights.append(
        CitedInsight(
            title="Get a full Muse Spark brief",
            action=(
                "Run a live analysis for content gaps and positioning; this snapshot only "
                "counts listings and prices."
            ),
            why="Snapshot briefs are computed in Python and do not read the pages with Muse.",
            priority="low",
        )
    )
    domain = urlparse(snap.get("source_url", url)).hostname or ""
    return CompetitorBrief(
        competitor_url=snap.get("source_url", url),
        competitor_domain=domain,
        seller_context="Art of Sarabjit Singh",
        summary=(
            f"Saved snapshot of {name} on {platform} (captured {captured}): {len(entries)} pages, "
            f"{buckets.get('products', 0)} product pages"
            + (f", prices ${prices[0]:.2f}–${prices[-1]:.2f}" if prices else "")
            + ". Computed in Python from the snapshot; no Muse call was made."
        ),
        product_categories=subjects,
        pricing_signals=pricing,
        new_product_frequency="Unknown: the snapshot has no listing dates.",
        competitor_gaps=gaps,
        actionable_insights=insights,
        signals=CompetitorSignals(
            competitor_domain=domain,
            total_urls=len(entries),
            bucket_counts=dict(buckets),
            usd_priced_pages=len(prices),
            usd_price_min=prices[0] if prices else None,
            usd_price_max=prices[-1] if prices else None,
        ),
    )


def demo_competitor_brief_for(url: str | None) -> CompetitorBrief:
    """Saved result for the requested competitor: its snapshot brief, else the SikhiArt brief."""
    if url and "sikhiart" not in url.lower():
        brief = snapshot_competitor_brief(url)
        if brief is not None:
            return brief
    return demo_competitor_brief()
