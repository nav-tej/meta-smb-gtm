"""Pydantic v2 models for Flow 2: Ad Creative Studio.

Request/response contract only; the service behind it is not built yet (see
src/services/ad_creative.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.intel import CompetitorBrief

Placement = Literal["facebook_feed", "instagram_feed", "instagram_story", "reels_cover"]


class ProductInfo(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = None
    price: str | None = None
    brand_notes: str = Field(default="", max_length=1000)


class GenerateAdsRequest(BaseModel):
    product: ProductInfo
    competitor_brief: CompetitorBrief
    placements: list[Placement] = Field(default_factory=lambda: ["facebook_feed"], min_length=1)
    variants_per_placement: int = Field(default=3, ge=1, le=6)


class Creative(BaseModel):
    placement: Placement
    image_path: str
    prompt: str
    headline: str
    primary_text: str
    produced_by: str = Field(description="Model or workflow that produced the image.")


class CreativeSet(BaseModel):
    product_title: str
    creatives: list[Creative]
