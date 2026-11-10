"""Tests for Track J: VoiceProfile extraction, similarity checking, and caption humanizer."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.voice import VoiceProfile
from src.services.accounts import AccountSession
from src.services.voice_profile import (
    adjust_voice_profile,
    build_voice_profile,
    check_inspiration_similarity,
    humanize_generated_caption,
)

USER_ID = "55555555-5555-4000-8000-555555555555"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


SAMPLE_SELLER_CAPTIONS = [
    "Just finished fresh wheel-thrown ceramic mugs and pottery! ☕ Available in my shop.",
    (
        "Each piece is glazed by hand in earthy sage and oatmeal tones. "
        "Perfect for your morning coffee."
    ),
    (
        "Loving how this ribbed texture turned out after the wood-fire kiln. "
        "Grab yours before they sell out! ✨"
    ),
    (
        "Packing up today's orders with handwritten notes and recyclable wrapping paper. "
        "Thank you for supporting solo makers!"
    ),
    "Sneak peek at new pottery coming from the studio this weekend. #pottery #ceramics",
]

SAMPLE_INSPIRATION_TEXTS = [
    "Our studio meticulously paints heirloom oil portraits with bespoke gold leaf frames.",
    "Every masterpiece stands as a testament to unrivaled renaissance craftsmanship.",
]


# ---------------------------------------------------------------------------
# 1. Voice profile extraction
# ---------------------------------------------------------------------------


def test_build_voice_profile_from_seller_texts() -> None:
    """Builds a VoiceProfile from seller captions, computing style traits and sample lines."""
    profile = build_voice_profile(
        seller_texts=SAMPLE_SELLER_CAPTIONS,
        sources=["instagram captions"],
    )

    assert isinstance(profile, VoiceProfile)
    assert 6.0 <= profile.avg_sentence_words <= 20.0
    assert profile.formality == "casual"  # "loving", "grab", "sneak peek"
    assert profile.uses_emojis is True
    assert "☕" in profile.common_emojis or "✨" in profile.common_emojis
    assert any("pottery" in w or "ceramics" in w or "mugs" in w for w in profile.recurring_words)
    assert 1 <= len(profile.sample_lines) <= 8

    # All sample lines must originate from the seller's captions
    for line in profile.sample_lines:
        assert any(line in caption for caption in SAMPLE_SELLER_CAPTIONS)


def test_inspiration_sources_shape_style_only_never_copied() -> None:
    """Inspiration texts adjust style parameters but are never stored in sample lines."""
    profile = build_voice_profile(
        seller_texts=SAMPLE_SELLER_CAPTIONS,
        inspiration_texts=SAMPLE_INSPIRATION_TEXTS,
        sources=["seller IG", "inspiration URL"],
    )

    # Sample lines MUST NOT contain inspiration sentences
    for line in profile.sample_lines:
        assert "heirloom oil portraits" not in line
        assert "renaissance craftsmanship" not in line


# ---------------------------------------------------------------------------
# 2. Similarity check against inspiration text
# ---------------------------------------------------------------------------


def test_check_inspiration_similarity_detects_plagiarism() -> None:
    """Detects when generated copy closely matches inspiration sentences."""
    # Plagiarized copy
    plagiarized = "Our studio meticulously paints heirloom oil portraits with custom gold leaf."
    is_plag, match = check_inspiration_similarity(plagiarized, SAMPLE_INSPIRATION_TEXTS)
    assert is_plag is True
    assert match is not None
    assert "heirloom oil portraits" in match

    # Clean, distinct copy
    original = "Handcrafted sage ceramic mug with textured wood-fired rim."
    is_plag_orig, match_orig = check_inspiration_similarity(original, SAMPLE_INSPIRATION_TEXTS)
    assert is_plag_orig is False
    assert match_orig is None


# ---------------------------------------------------------------------------
# 3. Caption humanizer cleaning
# ---------------------------------------------------------------------------


def test_humanize_generated_caption_applies_lint_and_shorter_adjustment() -> None:
    """Humanizer removes em dashes, buzzwords, and applies voice tuning."""
    raw_caption = (
        "Handmade ceramic mug — delve into our revolutionary collection of wheel-thrown pottery. "
        "Each mug is crafted with love. Grab yours today before they are all gone!"
    )

    profile = VoiceProfile(adjustments=["shorter"])
    cleaned = humanize_generated_caption(raw_caption, voice_profile=profile)

    # Em dash replaced
    assert "—" not in cleaned
    # Banned AI words cleaned / replaced
    assert "delve into" not in cleaned
    assert "revolutionary" not in cleaned
    # Shorter adjustment preserves at most 2 sentences
    sentences = [s.strip() for s in cleaned.split(".") if s.strip()]
    assert len(sentences) <= 2


def test_adjust_voice_profile_modifies_parameters() -> None:
    """Tuning with 'casual', 'formal', or 'shorter' updates voice profile targets."""
    prof = VoiceProfile(avg_sentence_words=16.0, formality="neutral")

    p_casual = adjust_voice_profile(prof, "casual")
    assert p_casual.formality == "casual"
    assert "casual" in p_casual.adjustments

    p_formal = adjust_voice_profile(prof, "formal")
    assert p_formal.formality == "formal"

    p_shorter = adjust_voice_profile(prof, "shorter")
    assert p_shorter.avg_sentence_words < prof.avg_sentence_words


# ---------------------------------------------------------------------------
# 4. Voice API endpoints
# ---------------------------------------------------------------------------


def test_voice_api_get_and_tune_endpoints(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """GET and POST /api/v1/voice endpoints manage VoiceProfile persistence."""
    user = AccountSession(
        user_id=USER_ID,
        email="artist@studio.test",
        email_verified=True,
        access_token="tok-voice",
        session_id=None,
    )
    workspace_store: dict[str, Any] = {"document": {}, "version": 1}

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {
            "document": workspace_store["document"],
            "version": workspace_store["version"],
            "owner_id": user.user_id,
        }

    async def fake_save(
        _account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        workspace_store["document"] = doc
        workspace_store["version"] += 1
        return {"document": doc, "version": workspace_store["version"], "owner_id": user.user_id}

    monkeypatch.setattr("src.api.voice.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.voice.load_workspace", fake_load)
    monkeypatch.setattr("src.api.voice.save_workspace", fake_save)

    headers = {"X-Muse-Owner": user.user_id}

    # 1. GET default profile
    get_resp = client.get("/api/v1/voice/profile", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["profile"]["formality"] == "neutral"

    # 2. POST /tune with 'casual'
    tune_resp = client.post(
        "/api/v1/voice/tune",
        json={"rating": "thumbs_up", "adjustment": "casual"},
        headers=headers,
    )
    assert tune_resp.status_code == 200
    tuned = tune_resp.json()
    assert tuned["profile"]["formality"] == "casual"
    assert "casual" in tuned["profile"]["adjustments"]
    assert workspace_store["document"]["voice_profile"]["formality"] == "casual"
