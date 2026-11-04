"""Pydantic v2 models for Flow 2: Ad Creative Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.models.intel import CompetitorBrief

Placement = Literal["facebook_feed", "instagram_feed", "instagram_story", "reels_cover"]
MuseWorkflowMode = Literal[
    "default",
    "product_visuals",
    "restore_enhance",
    "multi_image_combine",
]


class ProductInfo(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = None
    image_base64: str | None = Field(
        default=None,
        description="Optional base64-encoded product/artwork photo bytes when uploading directly.",
    )
    secondary_image_url: str | None = Field(
        default=None,
        description="Optional second product/style image URL for multi_image_combine workflows.",
    )
    secondary_image_base64: str | None = Field(
        default=None,
        description="Optional second base64 image for multi_image_combine diptych workflows.",
    )
    price: str | None = None
    brand_notes: str = Field(default="", max_length=1000)


class PlacementSpec(BaseModel):
    """Size requirements for a placement. Set from `placement`; edit the placement, not these."""

    width: int
    height: int
    aspect_ratio: str


class EditableCreativeVariant(BaseModel):
    """One proposed ad. Every text field can be edited before images are generated."""

    variant_id: str = Field(min_length=1, max_length=20)
    include: bool = Field(default=True, description="Set false to skip this variant.")
    placement: Placement
    spec: PlacementSpec | None = Field(
        default=None, description="Filled from `placement` by the server; edits are ignored."
    )
    target_audience: str = Field(default="", max_length=500, description="Who this ad is for.")
    headline: str = Field(min_length=1, max_length=120)
    primary_text: str = Field(min_length=1, max_length=600)
    image_prompt: str = Field(
        min_length=1,
        max_length=2000,
        description="Scene around the untouched artwork, sent to Muse Image as-is.",
    )
    motion_and_audio_prompt: str = Field(default="", max_length=1000)
    angle_rationale: str = Field(default="", max_length=500)


class EditableCreativeBrief(BaseModel):
    """Phase 1 of /generate-ads (draft=true): a proposed plan to review and edit.

    Send it back as `brief` to generate images from it without another Muse Spark call.
    """

    kind: Literal["draft"] = "draft"
    product_title: str
    positioning_hook: str = Field(min_length=1, max_length=300)
    preserve_product_note: str = Field(default="", max_length=500)
    variants: list[EditableCreativeVariant] = Field(min_length=1, max_length=12)
    estimated_paid_calls: int = Field(
        default=0,
        ge=0,
        description="Muse calls phase 2 will make: 1 per included variant, +1 SAM with an image.",
    )


class GenerateAdsRequest(BaseModel):
    """Run one-shot, or in two phases: `draft=true` first, then send the edited `brief` back."""

    product: ProductInfo
    competitor_brief: CompetitorBrief | None = Field(
        default=None, description="Required unless an edited `brief` is supplied."
    )
    draft: bool = Field(
        default=False,
        description="Return a proposed creative brief for review instead of generating images.",
    )
    brief: EditableCreativeBrief | None = Field(
        default=None,
        description="An edited brief from a draft=true call; images are generated from it.",
    )
    placements: list[Placement] = Field(default_factory=lambda: ["facebook_feed"], min_length=1)
    variants_per_placement: int = Field(default=3, ge=1, le=6)
    use_comfyui: bool = Field(
        default=True,
        description=(
            "Run ComfyUI workflows (e.g. Krea 3, Krea-2 Turbo, Ideogram 4, FLUX.1-Krea-dev, "
            "LTX-2.5 DFR, or MiniMax H3)."
        ),
    )
    comfyui_workflow: str = Field(
        default="krea3_scene_edit",
        description=(
            "ComfyUI image workflow under workflows/ (krea3_scene_edit, krea2_turbo_style_ref, "
            "ideogram4_collector_card, flux_krea_scene_relight, placement_outpaint)."
        ),
    )
    comfyui_video_workflow: str | None = Field(
        default=None,
        description=(
            "Optional ComfyUI video+audio workflow under workflows/ (ltx2_5_dfr_i2v or "
            "minimax_h3_i2v) to turn hero frames into 9:16/4:5 video ads."
        ),
    )
    use_muse_image_edit: bool = Field(
        default=False,
        description=(
            "When True and a reference image is provided, call POST /v1/images/edits "
            "(muse-image-1.0) to restage the seller's artwork/product photo directly."
        ),
    )
    muse_workflow_mode: MuseWorkflowMode = Field(
        default="default",
        description=(
            "Native Meta Model API Playground workflow mode on /v1/responses "
            "(product_visuals, restore_enhance, multi_image_combine) mirroring ComfyUI hub graphs."
        ),
    )

    @model_validator(mode="after")
    def _check_phase(self) -> GenerateAdsRequest:
        if self.draft and self.brief is not None:
            raise ValueError("Send draft=true to get a new brief, or an edited brief, not both.")
        if self.brief is None and self.competitor_brief is None:
            raise ValueError("competitor_brief is required unless an edited brief is supplied.")
        return self


class CreativeAngle(BaseModel):
    """Single Muse Spark creative concept tuned to a specific placement."""

    placement: Placement
    target_audience: str = Field(
        default="",
        description="Who this ad is for, in plain words (interests, life moment, buying intent).",
    )
    scene_prompt: str = Field(
        min_length=1,
        description="Collector room / lifestyle backdrop prompt around the untouched product.",
    )
    motion_and_audio_prompt: str = Field(
        default="",
        description=(
            "Optional camera motion and synchronized stereo audio direction for LTX-2.5 DFR "
            "or MiniMax H3 video generation."
        ),
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
    variant_id: str | None = None
    target_audience: str = ""
    image_path: str
    prompt: str
    headline: str
    primary_text: str
    produced_by: str = Field(description="Model or workflow that produced the creative.")
    media_type: Literal["image", "video"] = "image"
    reasoning_summary: str = Field(
        default="",
        description="Reasoning summary returned by muse-image-1.0 (/v1/responses) when used.",
    )
    media_data_url: str | None = Field(
        default=None,
        description=(
            "Inline base64 data URL for a newly generated image, so the browser does not need a "
            "second GET to the instance that wrote it. None for saved samples and videos."
        ),
    )
    media_mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None = Field(
        default=None, description="MIME type detected from the image bytes, not the extension."
    )


class CreativeSet(BaseModel):
    kind: Literal["creative_set"] = "creative_set"
    product_title: str
    creatives: list[Creative]
    mask_path: str | None = None
    positioning_hook: str = ""
