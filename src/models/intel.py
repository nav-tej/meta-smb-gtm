"""Pydantic v2 models for Flow 1: Competitor Intel."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

UrlBucket = Literal[
    "products",
    "listings",
    "collections",
    "blogs",
    "pages",
    "other",
]


class SitemapEntry(BaseModel):
    """A single discovered URL entry from a competitor sitemap or fallback page crawl."""

    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None
    title: str | None = None
    description: str | None = None
    price_hint: str | None = None
    bucket: UrlBucket = "other"


class CompetitorSignals(BaseModel):
    """Deterministic metrics computed in Python from crawled competitor URLs."""

    competitor_domain: str
    sitemaps_discovered: list[str] = Field(default_factory=list)
    total_urls: int = Field(ge=0)
    bucket_counts: dict[str, int] = Field(default_factory=dict)
    recent_30d_count: int = Field(default=0, ge=0)
    recent_90d_count: int = Field(default=0, ge=0)
    unknown_lastmod_count: int = Field(default=0, ge=0)
    growing_categories: list[str] = Field(default_factory=list)
    publishing_cadence_per_week: float | None = Field(default=None, ge=0)
    detected_price_hints: list[str] = Field(default_factory=list)
    seasonal_themes: list[str] = Field(default_factory=list)


class ActionableInsight(BaseModel):
    """A concrete, five-minute action an SMB seller can take based on competitor findings."""

    title: str = Field(min_length=1, description="Short headline for the recommended action.")
    action: str = Field(
        min_length=1,
        description=(
            "Plain-language next step (listing idea, collection page, blog post, or promo)."
        ),
    )
    why: str = Field(
        min_length=1,
        description="One-line explanation citing what was observed on the competitor site.",
    )
    priority: Literal["high", "medium", "low"] = "medium"


class BatchAnalysis(BaseModel):
    """Muse Spark structured findings for a single batch of competitor URLs and page titles."""

    product_categories: list[str] = Field(default_factory=list)
    pricing_signals: list[str] = Field(default_factory=list)
    content_strategy_patterns: list[str] = Field(default_factory=list)
    seo_keywords: list[str] = Field(default_factory=list)
    new_product_frequency: str = ""
    notable_gaps: list[str] = Field(default_factory=list)


class CompetitorBriefLLMOutput(BaseModel):
    """Structured output schema requested from Muse Spark when synthesizing a CompetitorBrief."""

    summary: str = Field(
        min_length=1,
        description="Plain-language 2-3 sentence overview written for a solo shop owner.",
    )
    product_categories: list[str] = Field(
        default_factory=list,
        description="Main and emerging product categories or niches spotted.",
    )
    pricing_signals: list[str] = Field(
        default_factory=list,
        description="Observed price points, size/format tiers, bundles, or promotional cues.",
    )
    content_strategy_patterns: list[str] = Field(
        default_factory=list,
        description="Recurring landing page, collection, gift guide, or blog patterns.",
    )
    seo_keywords: list[str] = Field(
        default_factory=list,
        description="High-intent search keywords and phrases extracted from URLs and titles.",
    )
    new_product_frequency: str = Field(
        min_length=1,
        description="Plain-language assessment of launch cadence grounded in the supplied metrics.",
    )
    doubling_down_on: list[str] = Field(
        default_factory=list,
        description="Themes, formats, or categories the competitor is actively investing in.",
    )
    competitor_gaps: list[str] = Field(
        default_factory=list,
        description=(
            "Underserved niches, missing content angles, or weaknesses the seller can exploit."
        ),
    )
    actionable_insights: list[ActionableInsight] = Field(
        min_length=1,
        max_length=7,
        description="3 to 5 concrete, plain-language actions with a one-line 'why' each.",
    )


class CompetitorIntelRequest(BaseModel):
    """Service/API input parameters for running a Competitor Intel analysis.

    `competitor_url` may be a site root (sitemap crawl) or a seller's profile/shop page.
    `pasted_urls` (also accepted as `urls`) adds specific pages, or is the only input.
    """

    competitor_url: str | None = Field(default=None, min_length=1)
    seller_context: str = ""
    pasted_urls: list[str] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices("pasted_urls", "urls"),
    )
    batch_size: int = Field(default=100, ge=1, le=500)
    max_batches: int = Field(default=5, ge=1, le=20)
    max_urls: int | None = Field(default=None, ge=1, le=10_000)
    fetch_titles: bool = True

    @model_validator(mode="after")
    def _require_a_source(self) -> CompetitorIntelRequest:
        if not self.competitor_url and not any(u.strip() for u in self.pasted_urls):
            raise ValueError("Provide competitor_url, a list of urls, or both.")
        return self


class CompetitorBrief(BaseModel):
    """Final structured competitive intelligence brief returned to the SMB seller."""

    competitor_url: str
    competitor_domain: str
    seller_context: str = ""
    summary: str
    product_categories: list[str] = Field(default_factory=list)
    pricing_signals: list[str] = Field(default_factory=list)
    content_strategy_patterns: list[str] = Field(default_factory=list)
    seo_keywords: list[str] = Field(default_factory=list)
    new_product_frequency: str
    doubling_down_on: list[str] = Field(default_factory=list)
    competitor_gaps: list[str] = Field(default_factory=list)
    actionable_insights: list[ActionableInsight] = Field(default_factory=list)
    signals: CompetitorSignals
    batches_analyzed: int = Field(default=0, ge=0)
