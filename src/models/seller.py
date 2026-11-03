"""Pydantic v2 models for the seller profile (who we are doing growth work for)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

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
