"""Tests for Item 11: Meta Ad Library Signals, Link-Outs, and Cache Layer.

Rules verified:
1. No token configured returns link-out only, zero fabricated rows, status='no_token'.
2. API zero returns status='zero' and 'No ads found via the Meta API.'
3. API failure returns status='error' with graceful error text (different from API zero).
4. Live records include library_url and start_date, and are cached via Track E cache.
5. Demo presets strictly label sample hooks with [sample].
6. Homepage displays 'See their ads on Meta ↗' links per competitor.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import Settings, get_settings
from src.services.research_cache import set_research_cache_dir


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_cache_and_overrides(tmp_path) -> None:
    set_research_cache_dir(tmp_path / "cache")
    app.dependency_overrides.clear()
    yield
    set_research_cache_dir(None)
    app.dependency_overrides.clear()


def test_no_token_returns_link_out_and_no_fabricated_rows(client: TestClient) -> None:
    """Without META_ADS_ACCESS_TOKEN, return link-out only and zero fabricated rows."""
    settings_no_token = Settings(meta_ads_access_token="")
    app.dependency_overrides[get_settings] = lambda: settings_no_token

    resp = client.get("/api/v1/competitors/ads?query=Desi+Canvas+Co")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "no_token"
    assert "not configured" in data["message"]
    assert data["total_active_ads"] == 0
    assert data["ads"] == []
    assert "facebook.com/ads/library" in data["public_library_url"]
    assert "q=Desi+Canvas+Co" in data["public_library_url"]


def test_api_zero_records_distinct_from_failure(client: TestClient) -> None:
    """When Meta API call succeeds but returns 0 ads, return 'No ads found via the Meta API.'"""
    settings_with_token = Settings(meta_ads_access_token="test_token_123")
    app.dependency_overrides[get_settings] = lambda: settings_with_token
    empty_payload = {"data": []}

    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(empty_payload).encode("utf-8"),
        request=httpx.Request("GET", "https://graph.facebook.com/v21.0/ads_archive"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        resp = client.get("/api/v1/competitors/ads?query=QuietStudioShop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "zero"
        assert data["message"] == "No ads found via the Meta API."
        assert data["total_active_ads"] == 0
        assert data["ads"] == []
        assert "q=QuietStudioShop" in data["public_library_url"]


def test_api_failure_returns_graceful_error_note(client: TestClient) -> None:
    """When Meta API call fails, return error status with different message from API zero."""
    settings_with_token = Settings(meta_ads_access_token="test_token_123")
    app.dependency_overrides[get_settings] = lambda: settings_with_token

    mock_error_resp = httpx.Response(
        status_code=500,
        content=b'{"error":{"message":"Internal server error"}}',
        request=httpx.Request("GET", "https://graph.facebook.com/v21.0/ads_archive"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_error_resp):
        resp = client.get("/api/v1/competitors/ads?query=ErrorProneBrand")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "Meta Ad Library request failed" in data["message"]
        # Must be different from the API zero message:
        assert data["message"] != "No ads found via the Meta API."
        assert data["total_active_ads"] == 0
        assert data["ads"] == []
        assert "q=ErrorProneBrand" in data["public_library_url"]


def test_api_live_records_and_cache(client: TestClient) -> None:
    """Live records include start_date and library_url, and second call is cached."""
    settings_with_token = Settings(meta_ads_access_token="test_token_123")
    app.dependency_overrides[get_settings] = lambda: settings_with_token
    live_payload = {
        "data": [
            {
                "id": "11223344",
                "page_name": "Artisan Table Co",
                "ad_delivery_start_time": "2026-09-01T00:00:00+0000",
                "publisher_platforms": ["instagram", "facebook"],
                "ad_creative_link_titles": ["Hand-Thrown Stoneware Mugs"],
                "ad_creative_bodies": ["Crafted with speckled clay. Free gift packaging."],
            }
        ]
    }

    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(live_payload).encode("utf-8"),
        request=httpx.Request("GET", "https://graph.facebook.com/v21.0/ads_archive"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        resp = client.get("/api/v1/competitors/ads?query=Artisan+Table+Co")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live"
        assert data["total_active_ads"] == 1
        assert data["is_cached"] is False
        assert len(data["ads"]) == 1
        ad = data["ads"][0]
        assert ad["ad_id"] == "11223344"
        assert ad["page_name"] == "Artisan Table Co"
        assert ad["library_url"] == "https://www.facebook.com/ads/library/?id=11223344"
        assert ad["start_date"] == "2026-09-01"
        assert mock_get.call_count == 1

        # Second request with same query must be a cache hit (0 external calls)
        resp2 = client.get("/api/v1/competitors/ads?query=Artisan+Table+Co")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["is_cached"] is True
        assert data2["total_active_ads"] == 1
        assert mock_get.call_count == 1  # Unchanged!


def test_demo_presets_sample_hooks_labeled(client: TestClient) -> None:
    """Verify demo presets strictly label sample hooks with [sample]."""
    resp = client.get("/api/v1/demo-presets")
    assert resp.status_code == 200
    data = resp.json()

    for ws_id in ["sarabjit_singh", "etsy_ceramics"]:
        ws = data["workspaces"][ws_id]
        meta_ads = ws.get("meta_ads_signals") or {}
        assert meta_ads.get("is_sample") is True
        hooks = meta_ads.get("sample_hooks") or []
        assert len(hooks) > 0
        for hook in hooks:
            assert hook.startswith("[sample]"), f"Hook must be labeled [sample]: {hook}"


def test_homepage_competitor_links(client: TestClient) -> None:
    """Verify index.html includes public Meta Ad Library links for competitors."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "https://www.facebook.com/ads/library/?active_status=active" in html
    assert "q=SikhiArt" in html
    assert "q=Gurinderpreet%20Kaur" in html
    assert "q=Manjot%20Singh%20Sachdeva" in html
    assert "q=Gurdish%20Pannu" in html
    assert "See their ads on Meta ↗" in html
