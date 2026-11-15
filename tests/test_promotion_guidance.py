"""Unit tests for truthful promotion guidance and handoff defaults."""

from __future__ import annotations

from src.models.seller import (
    AccessPreferences,
    PromotionGuidanceSummary,
    SellerPreferences,
    TastePreferences,
)
from src.services.seller_memory import rank_seller_recommendations


def test_recommendations_emit_truthful_labels_and_missing_facts() -> None:
    pref = SellerPreferences(
        goals=["sales"],
        taste=TastePreferences(
            preferred_channels=["instagram"],
            tone="warm",
            caption_length="short",
        ),
        access=AccessPreferences(minutes_per_week=60),
    )
    result = rank_seller_recommendations(
        business_name="Wild Meadow Press",
        preferences=pref,
    )
    recs = result["recommendations"]
    assert recs
    first = recs[0]
    assert first["output_provenance"] == "suggested_starting_approach"
    assert first["output_label"] == "Suggested starting approach"
    assert "Fresh Muse analysis" not in first["output_label"]
    assert first["organic_first"] is True
    assert first["organic_guidance_note"]
    assert first["audience_confirmed"] is False
    assert first["unconfirmed_audience"].startswith("Unconfirmed starting hypothesis")
    assert first["missing_facts"]
    joined_missing = " ".join(first["missing_facts"]).lower()
    assert "price" in joined_missing
    assert "product" in joined_missing
    assert "audience" in joined_missing

    ed = first["editor_defaults"]
    assert ed["output_provenance"] == "suggested_starting_approach"
    assert ed["output_label"] == "Suggested starting approach"
    assert ed["organic_first"] is True
    assert ed["audience_confirmed"] is False
    assert ed["placement_note"] == "App export preset (not verified Meta policy)"
    assert ed["price_claim"] == ""
    assert isinstance(ed["approved_facts"], list)


def test_draft_override_does_not_mutate_saved_memory() -> None:
    pref = SellerPreferences(
        goals=["story"],
        taste=TastePreferences(
            preferred_channels=["instagram"],
            tone="warm",
            caption_length="short",
            words_to_avoid=["luxury"],
        ),
        access=AccessPreferences(minutes_per_week=90),
    )
    result = rank_seller_recommendations(
        business_name="Cedar Kiln Ceramics",
        preferences=pref,
        draft_override={
            "tone": "direct",
            "caption_length": "long",
            "destination": "etsy",
            "words_to_avoid": ["cheap"],
        },
    )
    recs = result["recommendations"]
    assert recs
    ed = recs[0]["editor_defaults"]
    assert ed["tone"] == "direct"
    assert ed["caption_length"] == "long"
    assert ed["destination"] == "etsy"
    # Saved preferences remain untouched.
    assert pref.taste.tone == "warm"
    assert pref.taste.caption_length == "short"
    assert pref.taste.words_to_avoid == ["luxury"]


def test_promotion_guidance_summary_model_defaults() -> None:
    summary = PromotionGuidanceSummary(
        business_name="Wild Meadow Press",
        selected_goal="story",
        unconfirmed_audience=(
            "Unconfirmed starting hypothesis (edit before sharing): people looking for gifts"
        ),
        missing_facts=["Price is not set"],
    )
    assert summary.output_provenance == "suggested_starting_approach"
    assert summary.output_label == "Suggested starting approach"
    assert summary.organic_first is True
    assert summary.audience_confirmed is False
    assert summary.placement_note == "App export preset (not verified Meta policy)"
