"""Offline regression test suite for the Storefront Import flow (/api/v1/ingest-storefront).

Validates client-side DOM contracts via Node.js VM harness and backend API contracts
for domain blocking, error handling, payload normalization, and schema validation.
Strictly offline: all external HTTP calls are forbidden.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_creator_import_smoke_node_runner() -> None:
    """Execute tests/creator_import_sprint.cjs via Node.js VM harness."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute creator_import_sprint.cjs")

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            node,
            str(root / "tests/creator_import_sprint.cjs"),
            str(root / "src/api/static/creator.js"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ALL 5 STOREFRONT IMPORT QA TEST SCENARIOS PASSED" in result.stdout


def test_ingest_storefront_blocked_domains_offline(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Marketplace & social URLs (etsy, instagram, facebook) are caught without network calls."""

    async def forbid_network(*args, **kwargs):
        raise AssertionError("Crawler must not make network calls for known blocked domains")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid_network)

    payload = {
        "business_name": "Test Clay Studio",
        "website_url": "https://www.etsy.com/shop/testclay",
        "max_urls_per_source": 30,
    }
    resp = client.post("/api/v1/ingest-storefront", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["business_name"] == "Test Clay Studio"
    assert len(data["channels"]) == 1
    channel = data["channels"][0]
    assert channel["status"] == "vision_or_manual"
    assert channel["pages_found"] == 0
    assert "blocks automated crawlers" in channel["note"]
    assert data["discovered_catalog_items"] == []


def test_ingest_storefront_social_and_marketplace_separation(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Verify multiple channel sources populate channels with vision_or_manual status."""

    async def forbid_network(*args, **kwargs):
        raise AssertionError("Crawler must not make external requests in this test")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid_network)

    payload = {
        "business_name": "Saffron & Clay",
        "website_url": "https://instagram.com/saffronclay",
        "marketplace_urls": ["https://etsy.com/shop/saffronclay"],
        "social_urls": ["https://facebook.com/saffronclay"],
    }
    resp = client.post("/api/v1/ingest-storefront", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_channels"] == 3
    for ch in data["channels"]:
        assert ch["status"] == "vision_or_manual"
        assert ch["pages_found"] == 0


def test_ingest_storefront_validation_limits(client: TestClient) -> None:
    """Verify pydantic field validation boundaries (lengths, bounds)."""
    # Business name exceeding 160 characters
    oversized_name = "A" * 161
    resp = client.post(
        "/api/v1/ingest-storefront",
        json={"business_name": oversized_name, "website_url": "https://example.com"},
    )
    assert resp.status_code == 422
    assert "business_name" in resp.text

    # Max URLs out of bounds (< 5 or > 100)
    resp_low = client.post(
        "/api/v1/ingest-storefront",
        json={"website_url": "https://example.com", "max_urls_per_source": 2},
    )
    assert resp_low.status_code == 422

    resp_high = client.post(
        "/api/v1/ingest-storefront",
        json={"website_url": "https://example.com", "max_urls_per_source": 150},
    )
    assert resp_high.status_code == 422


def test_ingest_storefront_mock_successful_crawl(monkeypatch, client: TestClient) -> None:
    """Verify mock crawl produces the expected discovered_catalog_items and seller_context."""
    from src.api import intel
    from src.models.intel import SitemapEntry

    async def mock_collect_entries(*args, **kwargs):
        entries = [
            SitemapEntry(
                loc="https://mystore.example/products/handcrafted-bowl",
                title="Handcrafted Ceramic Bowl",
                bucket="products",
                price_hint="$42",
            ),
            SitemapEntry(
                loc="https://mystore.example/products/stoneware-mug",
                title="Stoneware Coffee Mug",
                bucket="products",
                price_hint="$24",
            ),
        ]
        sitemaps = ["https://mystore.example/sitemap.xml"]
        return entries, sitemaps

    monkeypatch.setattr(intel, "collect_entries", mock_collect_entries)

    payload = {
        "business_name": "My Mountain Pottery",
        "website_url": "https://mystore.example",
        "max_urls_per_source": 30,
    }
    resp = client.post("/api/v1/ingest-storefront", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["business_name"] == "My Mountain Pottery"
    assert data["total_pages_crawled"] == 2
    assert len(data["discovered_catalog_items"]) == 2

    item1 = data["discovered_catalog_items"][0]
    assert item1["title"] == "Handcrafted Ceramic Bowl"
    assert item1["price_hint"] == "$42"
    assert item1["url"] == "https://mystore.example/products/handcrafted-bowl"

    assert "$42" in data["detected_price_hints"]
    assert "$24" in data["detected_price_hints"]
    assert "My Mountain Pottery" in data["seller_context"]
    assert "Handcrafted Ceramic Bowl" in data["seller_context"]
