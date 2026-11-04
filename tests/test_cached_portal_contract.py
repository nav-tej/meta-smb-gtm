"""Public demo contracts: render the portal and return saved data without external I/O."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.bids import BidRecommendation
from src.models.creative import CreativeSet
from src.models.intel import CompetitorBrief
from src.services.ad_creative import AdCreativeService
from src.services.bid_advisor import BidAdvisorService
from src.services.competitor_intel import CompetitorIntelService

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


@pytest.fixture
def cached_portal(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEMO_MODE", "true")
    # A configured key must never cause demo requests to bypass the spending guard.
    monkeypatch.setenv("META_MODEL_API_KEY", "fake-key-never-send")
    get_settings.cache_clear()
    denied = AsyncMock(side_effect=AssertionError("Cached requests must not call live services"))
    monkeypatch.setattr(CompetitorIntelService, "analyze", denied)
    monkeypatch.setattr(AdCreativeService, "generate", denied)
    monkeypatch.setattr(AdCreativeService, "draft", denied)
    monkeypatch.setattr(BidAdvisorService, "advise", denied)
    monkeypatch.setattr(
        httpx.AsyncClient,
        "send",
        AsyncMock(side_effect=AssertionError("Cached requests must not send outbound HTTP")),
    )
    with TestClient(app) as client:
        yield client
    denied.assert_not_awaited()
    get_settings.cache_clear()


def test_root_serves_the_complete_single_file_portal(cached_portal: TestClient) -> None:
    response = cached_portal.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == (ROOT / "src/api/static/index.html").read_text()
    for marker in ("tab-intel", "tab-creative", "tab-bids", "Saved Muse outputs", "requestStatus"):
        assert marker in response.text


@pytest.mark.parametrize("query", ["", "?live=false"])
def test_competitor_returns_saved_brief_without_crawling(
    cached_portal: TestClient, query: str
) -> None:
    response = cached_portal.post(
        f"/api/v1/analyze-competitors{query}",
        json={"competitor_url": "https://does-not-exist.invalid/"},
    )
    expected = CompetitorBrief.model_validate_json(
        (SAMPLES / "competitor_brief_sikhiart_live.json").read_text()
    )
    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")


@pytest.mark.parametrize("query", ["", "?live=false"])
def test_one_shot_creative_returns_saved_copy_and_accessible_sample_image(
    cached_portal: TestClient, brief_json: dict[str, Any], query: str
) -> None:
    response = cached_portal.post(
        f"/api/v1/generate-ads{query}",
        json={"product": {"title": "Demo artwork"}, "competitor_brief": brief_json},
    )
    assert response.status_code == 200
    result = CreativeSet.model_validate(response.json())
    saved = CreativeSet.model_validate_json(
        (SAMPLES / "ad_creative_ek_onkar_live.json").read_text()
    )
    assert result.product_title == "Demo artwork"
    assert result.positioning_hook == saved.positioning_hook
    assert len(result.creatives) == len(saved.creatives)
    for actual, source in zip(result.creatives, saved.creatives, strict=True):
        assert actual.headline == source.headline
        assert actual.primary_text == source.primary_text
        assert actual.prompt == source.prompt
        assert actual.produced_by == "demo-cache (saved muse-image-1.0 output)"
        assert actual.image_path.startswith("samples/")
        image_response = cached_portal.get(f"/{actual.image_path}")
        assert image_response.status_code == 200
        assert image_response.content == (ROOT / "data" / actual.image_path).read_bytes()


@pytest.mark.parametrize("query", ["", "?live=false"])
def test_bid_advice_returns_the_saved_recommendation(
    cached_portal: TestClient, brief_json: dict[str, Any], query: str
) -> None:
    response = cached_portal.post(
        f"/api/v1/bid-advice{query}",
        json={
            "campaign": json.loads((SAMPLES / "sarabjit_singh_campaign.json").read_text()),
            "competitor_brief": brief_json,
        },
    )
    expected = BidRecommendation.model_validate_json((SAMPLES / "bid_advice_live.json").read_text())
    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
