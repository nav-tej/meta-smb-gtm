"""Boundaries for a small, channel-aware daily content plan."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Channel = Literal["instagram", "facebook", "x", "tiktok"]
ContentFormat = Literal["image", "video", "text"]


class PlanProduct(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=1500)
    price: str | None = Field(default=None, max_length=40)
    destination_url: str | None = Field(default=None, max_length=2000)
    seller: str = Field(default="", max_length=120)
    collection: str = Field(default="", max_length=120)

    @field_validator("destination_url")
    @classmethod
    def validate_destination(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError("Use a complete http or https destination without credentials.")
        return value


class EnteredPerformance(BaseModel):
    views: int = Field(default=0, ge=0, le=1_000_000_000)
    clicks: int = Field(default=0, ge=0, le=1_000_000_000)
    inquiries: int = Field(default=0, ge=0, le=1_000_000_000)
    sales: int = Field(default=0, ge=0, le=1_000_000_000)


class ContentPlanRequest(BaseModel):
    product: PlanProduct
    channels: list[Channel] = Field(
        default_factory=lambda: ["instagram", "facebook"], min_length=1, max_length=4
    )
    goal: Literal["visits", "inquiries", "sales"] = "visits"
    sales_goal: int | None = Field(default=None, ge=1, le=1_000_000)
    performance: EnteredPerformance | None = None
    use_muse: bool = False

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value: list[Channel]) -> list[Channel]:
        return list(dict.fromkeys(value))


class ContentPost(BaseModel):
    day_offset: Literal[0, 2, 4]
    channel: Channel
    format: ContentFormat
    hook: str = Field(min_length=1, max_length=180)
    caption: str = Field(min_length=1, max_length=1200)
    cta: str = Field(min_length=1, max_length=220)
    visual_direction: str = Field(min_length=1, max_length=500)
    posting_tip: str = Field(min_length=1, max_length=400)

    @model_validator(mode="after")
    def supported_format(self) -> ContentPost:
        if self.channel == "instagram" and self.format == "text":
            raise ValueError("An Instagram post needs an image or video.")
        if self.channel == "tiktok" and self.format != "video":
            raise ValueError("This TikTok plan uses a video shot list.")
        if self.channel == "x" and len(f"{self.hook}\n{self.caption}\n{self.cta}") > 230:
            raise ValueError("Keep X copy under 230 characters before a destination link.")
        return self


class ContentPlanDraft(BaseModel):
    recommended_channel: Channel
    recommended_format: ContentFormat
    reason: str = Field(min_length=1, max_length=500)
    posts: list[ContentPost] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def three_spaced_posts(self) -> ContentPlanDraft:
        if sorted(post.day_offset for post in self.posts) != [0, 2, 4]:
            raise ValueError("Provide one post each for day 0, 2 and 4.")
        first = next(post for post in self.posts if post.day_offset == 0)
        if (first.channel, first.format) != (self.recommended_channel, self.recommended_format):
            raise ValueError("Today's post must match the recommendation.")
        return self


class ContentInsight(BaseModel):
    source: Literal["not_connected", "user_entered"]
    summary: str
    next_action: str
    click_through_rate_pct: float | None = None
    click_to_sale_rate_pct: float | None = None
    sales_remaining: int | None = None


class GuidanceSource(BaseModel):
    title: str
    url: str


class ContentPlan(ContentPlanDraft):
    mode: Literal["starter", "muse"]
    insight: ContentInsight
    sources: list[GuidanceSource]
