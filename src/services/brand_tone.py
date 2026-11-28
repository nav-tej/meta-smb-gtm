"""Single source of truth for seller brand-tone choices and writing guides."""

from __future__ import annotations

from typing import NamedTuple


class BrandTone(NamedTuple):
    value: str
    label: str
    guide: str


BRAND_TONES: dict[str, BrandTone] = {
    "warm_story": BrandTone(
        value="warm_story",
        label="Warm & story-led",
        guide="Share the personal story and care behind the work in a friendly, grounded voice.",
    ),
    "expert_clear": BrandTone(
        value="expert_clear",
        label="Expert & clear",
        guide="Lead with plain, practical value and explain clearly how it helps.",
    ),
    "polished_premium": BrandTone(
        value="polished_premium",
        label="Polished & premium",
        guide="Use calm, refined phrasing that highlights craft, detail and quality.",
    ),
    "direct_offer": BrandTone(
        value="direct_offer",
        label="Direct & offer-led",
        guide="State what you offer, who it helps and the next step right away.",
    ),
}

LEGACY_TONE_MAP: dict[str, str] = {
    "collector_gallery": "polished_premium",
    "direct_gift": "direct_offer",
}


def normalize_tone(value: str | None) -> str | None:
    """Return a known brand-tone key or None (ignoring voice-profile and unknown values)."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    if not key:
        return None
    mapped = LEGACY_TONE_MAP.get(key, key)
    return mapped if mapped in BRAND_TONES else None


def tone_prompt_line(value: str | None) -> str | None:
    """Return the one-line tone directive for prompts/brand_notes, or None."""
    norm = normalize_tone(value)
    if not norm:
        return None
    tone = BRAND_TONES[norm]
    return f"Tone: {tone.label}. {tone.guide}"
