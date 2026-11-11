"""Pydantic v2 models for the seller profile (who we are doing growth work for)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.models.intel import ActionableInsight

FetchStatus = Literal["fetched", "partial", "access_denied", "robots_disallowed", "not_attempted"]


class PlatformPresence(BaseModel):
    platform: str
    url: str
    role: str = Field(description="What the seller uses it for, e.g. 'print-on-demand shop'.")
    fetch_status: FetchStatus
    notes: str = ""
    collections: list[str] = Field(default_factory=list)


class PriceOffer(BaseModel):
    product: str
    price_usd: float = Field(ge=0)
    size: str | None = None
    edition_size: int | None = Field(default=None, ge=1)
    notes: str = ""


class ArtSeries(BaseModel):
    name: str
    source_url: str
    summary: str
    works: list[str] = Field(default_factory=list)
    original_format: str | None = None
    direct_sale_offers: list[PriceOffer] = Field(default_factory=list)


class Artwork(BaseModel):
    title: str
    urls: dict[str, str] = Field(description="Platform name -> listing URL.")
    medium: str | None = None
    description: str | None = None
    series: str | None = None
    uploaded: date | None = None
    comment_count: int | None = Field(default=None, ge=0)
    print_from_usd: float | None = Field(default=None, ge=0)
    original_price_usd: float | None = Field(default=None, ge=0)
    original_sold: bool | None = None
    product_starting_prices_usd: dict[str, float] = Field(default_factory=dict)


class SellerProfile(BaseModel):
    """Snapshot of a seller's public catalog and presence, captured from their own pages."""

    snapshot_date: date
    name: str
    business_name: str
    location: str
    bio: str
    artist_statement: str
    mediums: list[str]
    themes: list[str]
    platforms: list[PlatformPresence]
    series: list[ArtSeries]
    artworks: list[Artwork]
    catalog_notes: list[str] = Field(default_factory=list)
    exhibitions: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    public_art: list[str] = Field(default_factory=list)

    def price_points(self) -> dict[str, tuple[float, float]]:
        """Min/max USD per price type across the catalog, for prompts and reports."""
        buckets: dict[str, list[float]] = {
            "marketplace_prints": [a.print_from_usd for a in self.artworks if a.print_from_usd],
            "originals": [a.original_price_usd for a in self.artworks if a.original_price_usd],
            "direct_limited_editions": [
                o.price_usd for s in self.series for o in s.direct_sale_offers
            ],
        }
        return {name: (min(v), max(v)) for name, v in buckets.items() if v}

    def to_seller_context(self) -> str:
        """Compact plain-text summary passed to Muse Spark as `seller_context`."""
        prices = "; ".join(
            f"{name.replace('_', ' ')} ${lo:,.0f}-${hi:,.0f}"
            for name, (lo, hi) in self.price_points().items()
        )
        live = [p.platform for p in self.platforms]
        return (
            f"{self.name} ({self.business_name}), {self.location}. "
            f"Mediums: {', '.join(self.mediums)}. Themes: {', '.join(self.themes)}. "
            f"Series: {', '.join(s.name for s in self.series)}. "
            f"Sells on: {', '.join(live)}. Price points: {prices}. "
            f"{len(self.artworks)} artworks in this snapshot."
        )


class AccessPreferences(BaseModel):
    channels: list[str] = Field(default_factory=list)
    can_change_prices: bool = True
    ads_budget_band: str | None = None
    minutes_per_week: int | None = Field(default=None, ge=0)


class TastePreferences(BaseModel):
    tone: str | None = None
    subjects_to_avoid: list[str] = Field(default_factory=list)
    price_positioning: Literal["budget", "mid", "premium"] | None = None

    @field_validator("subjects_to_avoid", mode="before")
    @classmethod
    def _coerce_avoid(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        if isinstance(v, list):
            return [str(part).strip() for part in v if str(part).strip()]
        return []


MemoryKind = Literal["observation", "interpretation", "preference", "goal"]
MemoryScope = Literal["shop_default", "product", "campaign", "draft"]
CompetitorRole = Literal["similar_audience", "price_reference", "inspiration"]
MemorySource = Literal[
    "shop_scan",
    "user_input",
    "voice_transcript",
    "voice_demo_fixture",
    "onboarding_questions",
    "feedback_suggestion",
    "sample_snapshot",
]


class SellerMemoryEntry(BaseModel):
    """Single inspectable, editable, and removable seller memory item."""

    id: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(max_length=320)
    kind: MemoryKind = "preference"
    scope: MemoryScope = "shop_default"
    product_key: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=80)
    source: MemorySource = "user_input"
    source_url: str | None = Field(default=None, max_length=500)
    scan_date: str | None = Field(default=None, max_length=40)
    confidence: Literal["observed", "inferred", "confirmed", "uncertain"] = "confirmed"
    uncertainty: str = Field(default="", max_length=240)
    status: Literal["proposed", "accepted", "dismissed"] = "accepted"
    seller_edited: bool = False
    updated_at: str | None = Field(default=None, max_length=40)


class SellerMemoryDiffItem(BaseModel):
    """Before/after diff entry produced when re-scanning a storefront."""

    entry_id: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    kind: MemoryKind
    before_value: str | None = None
    after_value: str | None = None
    source_url: str | None = None
    scan_date: str | None = None
    change_type: Literal["added", "changed", "unchanged", "removed"]
    preserves_seller_edit: bool = False


class CompetitorEntry(BaseModel):
    """Watched competitor with editable role and rationale separate from seller profile."""

    name: str = Field(default="", max_length=140)
    url: str = Field(min_length=1, max_length=500)
    role: CompetitorRole = "similar_audience"
    rationale: str = Field(default="", max_length=280)
    reason: str = Field(default="", max_length=280)
    selected: bool = True


class SuggestedMemoryUpdate(BaseModel):
    """Pending feedback-derived update requiring explicit seller approval."""

    id: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=140)
    proposed_value: str = Field(max_length=240)
    kind: MemoryKind = "preference"
    reason_signal: str = Field(max_length=280)
    source: Literal["feedback_suggestion"] = "feedback_suggestion"
    patch: dict[str, Any] = Field(default_factory=dict)
    dismiss_count: int = Field(default=0, ge=0)
    status: Literal["pending", "approved", "dismissed"] = "pending"
    created_at: str | None = Field(default=None, max_length=40)


class DismissSignal(BaseModel):
    id: str = ""
    title: str = ""
    channel: str | None = None
    reason: Literal[
        "not_my_style",
        "too_advanced",
        "no_access",
        "already_tried",
        "too_much_time",
        "wrong_channel",
        "",
    ] = ""
    at: str | None = None


class SellerPreferences(BaseModel):
    """Seller growth preferences and taste constraints for idea ranking and prompts."""

    experience: Literal["new", "some", "runs_ads"] = "some"
    access: AccessPreferences = Field(default_factory=AccessPreferences)
    taste: TastePreferences = Field(default_factory=TastePreferences)
    research_focus: str | None = Field(default=None, max_length=300)
    watch: list[str] = Field(default_factory=list)
    goal: str | None = Field(default=None, max_length=200)
    occasion: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=180)
    context_note: str | None = Field(default=None, max_length=600)
    memory_entries: list[SellerMemoryEntry] = Field(default_factory=list)
    competitor_entries: list[CompetitorEntry] = Field(default_factory=list)
    suggested_updates: list[SuggestedMemoryUpdate] = Field(default_factory=list)
    last_scan_at: str | None = Field(default=None, max_length=40)
    version: int = 1

    @field_validator("watch", mode="before")
    @classmethod
    def _coerce_watch(cls, v: Any) -> list[str]:
        if isinstance(v, dict):
            urls = v.get("competitor_urls") or []
            return [str(u).strip() for u in urls if str(u).strip()]
        if isinstance(v, list):
            return [str(u).strip() for u in v if str(u).strip()]
        return []


class ScreenshotAnalysis(BaseModel):
    """Multimodal Muse Spark Vision findings from IG, FB, Marketplace, or shop screenshots."""

    platform_detected: str = Field(min_length=1)
    visual_merchandising_hooks: list[str] = Field(default_factory=list)
    pricing_and_offer_signals: list[str] = Field(default_factory=list)
    copy_and_seo_keywords: list[str] = Field(default_factory=list)
    conversion_friction_or_gaps: list[str] = Field(default_factory=list)
    actionable_insights: list[ActionableInsight] = Field(default_factory=list)


class SellerDiagnostics(BaseModel):
    """Deterministic Python diagnostics across a seller's website, marketplaces, and social."""

    total_platforms: int = Field(ge=0)
    crawlable_platforms: list[str] = Field(default_factory=list)
    blocked_or_social_platforms: list[str] = Field(default_factory=list)
    total_artworks_indexed: int = Field(ge=0)
    artworks_missing_original_price: int = Field(ge=0)
    artworks_missing_series_tag: int = Field(ge=0)
    lowest_pod_print_usd: float | None = None
    highest_direct_edition_usd: float | None = None
    has_direct_checkout_gap: bool = False


class SellerFootprintAuditLLM(BaseModel):
    """Muse Spark structured recommendations for fixing a seller's multi-channel presence."""

    executive_summary: str = Field(min_length=1)
    website_seo_and_conversion_fixes: list[ActionableInsight] = Field(min_length=1, max_length=6)
    marketplace_and_pricing_fixes: list[ActionableInsight] = Field(min_length=1, max_length=6)
    instagram_and_facebook_sales_plays: list[ActionableInsight] = Field(min_length=1, max_length=6)


class SellerFootprintAudit(BaseModel):
    """Complete own-site + marketplace + IG/FB growth audit for an SMB seller."""

    seller_name: str
    business_name: str
    diagnostics: SellerDiagnostics
    executive_summary: str
    website_seo_and_conversion_fixes: list[ActionableInsight] = Field(default_factory=list)
    marketplace_and_pricing_fixes: list[ActionableInsight] = Field(default_factory=list)
    instagram_and_facebook_sales_plays: list[ActionableInsight] = Field(default_factory=list)
