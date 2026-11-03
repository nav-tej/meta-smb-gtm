"""Pydantic v2 models for Flow 2: Ad Creative Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.intel import CompetitorBrief

Placement = Literal["facebook_feed", "instagram_feed", "instagram_story", "reels_cover"]


class ProductInfo(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = None
    image_base64: str | None = Field(
        default=None,
        description="Optional base64-encoded product/artwork photo bytes when uploading directly.",
    )
    price: str | None = None
    brand_notes: str = Field(default="", max_length=1000)


class GenerateAdsRequest(BaseModel):
    product: ProductInfo
    competitor_brief: CompetitorBrief
    placements: list[Placement] = Field(default_factory=lambda: ["facebook_feed"], min_length=1)
    variants_per_placement: int = Field(default=3, ge=1, le=6)
    use_comfyui: bool = Field(
        default=True,
        description="Run open-weight ComfyUI workflows (e.g. FLUX.1-Krea-dev relight/outpaint).",
    )
    comfyui_workflow: str = Field(
        default="flux_krea_scene_relight",
        description="ComfyUI workflow name under workflows/ for open-weight variant generation.",
    )


class CreativeAngle(BaseModel):
    """Single Muse Spark creative concept tuned to a specific placement."""

    placement: Placement
    scene_prompt: str = Field(
        min_length=1,
        description="Collector room / lifestyle backdrop prompt around the untouched product.",
    )
    headline: str = Field(min_length=1, max_length=120)
    primary_text: str = Field(min_length=1, max_length=600)
    angle_rationale: str = Field(
        default="",
        description="One-line note tying this angle to a competitor gap or buyer hook.",
    )


class CreativeBrief(BaseModel):
    """Structured creative brief written by Muse Spark before image generation."""

    positioning_hook: str = Field(min_length=1)
    preserve_product_note: str = Field(min_length=1)
    angles: list[CreativeAngle] = Field(min_length=1)


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
    mask_path: str | None = None
    positioning_hook: str = ""
