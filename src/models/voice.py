"""Track J: Seller Voice Profile models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FormalityLevel = Literal["casual", "neutral", "formal"]
VoiceAdjustment = Literal["casual", "formal", "shorter"]
CaptionLengthPref = Literal["short", "medium", "detailed"]


class VoiceProfile(BaseModel):
    """Normalized stylistic voice traits derived from the seller's public content.

    Stores style parameters and short sample lines from the seller's own listings,
    never full copies of external inspiration posts.
    """

    model_config = ConfigDict(extra="allow")

    avg_sentence_words: float = Field(default=14.0, ge=3.0, le=50.0)
    formality: FormalityLevel = "neutral"
    uses_emojis: bool = False
    common_emojis: list[str] = Field(default_factory=list, max_length=10)
    avg_hashtags: int = Field(default=0, ge=0, le=30)
    common_hashtags: list[str] = Field(default_factory=list, max_length=10)
    recurring_words: list[str] = Field(default_factory=list, max_length=20)
    words_to_avoid: list[str] = Field(default_factory=list, max_length=30)
    phrases_to_avoid: list[str] = Field(default_factory=list, max_length=30)
    preferred_cta_style: str | None = Field(default=None, max_length=120)
    caption_length: CaptionLengthPref | None = None
    sample_lines: list[str] = Field(default_factory=list, max_length=8)
    sources: list[str] = Field(default_factory=list, max_length=5)
    adjustments: list[VoiceAdjustment] = Field(default_factory=list, max_length=10)
