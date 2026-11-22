"""Guards for the two public website scans (POST /ingest-storefront and /seller-memory/scan).

Both scans need no sign-in, and each request can crawl up to 21 (or 11) websites. With
SCAN_CACHE_SECONDS a successful crawl of the same website is reused, and with
SCANS_PER_VISITOR_PER_10_MIN a visitor over the cap is refused before any crawl starts. Both are
off by default, which must leave the scans exactly as they were.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.models.intel import SitemapEntry
from src.services import scan_guard
from src.utils.sitemap import SitemapError


@pytest.fixture
def scans(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"crawled": [], "fail": set(), "clock": 1000.0}

    async def fake_collect(url: str | None, *, max_urls: int | None = None, **_kwargs: Any):
        # Like the real crawl, keep the first `max_urls` pages (the site has 35).
        state["crawled"].append(url)
        if url in state["fail"]:
            raise SitemapError("No sitemap or crawlable pages found")
        return (
            [
                SitemapEntry(
                    loc=f"{url}/products/print-{n}",
                    title=f"Print {n}",
                    price_hint="$28",
                    bucket="products",
                )
                for n in range(min(max_urls or 35, 35))
            ],
            [f"{url}/sitemap.xml"],
        )

    monkeypatch.setattr("src.api.intel.collect_entries", fake_collect)
    monkeypatch.setattr("src.api.seller_memory.collect_entries", fake_collect)
    monkeypatch.setattr(scan_guard, "_now", lambda: state["clock"])
    scan_guard.reset()
    yield state
    scan_guard.reset()


def _configure(monkeypatch: pytest.MonkeyPatch, *, cache: int = 0, cap: int = 0) -> None:
    monkeypatch.setenv("SCAN_CACHE_SECONDS", str(cache))
    monkeypatch.setenv("SCANS_PER_VISITOR_PER_10_MIN", str(cap))
    get_settings.cache_clear()


def _ingest(client: TestClient, url: str, visitor: str = "203.0.113.5", **extra: Any):
    body = {"business_name": "Wild Meadow Prints", "website_url": url, **extra}
    return client.post("/api/v1/ingest-storefront", json=body, headers={"X-Forwarded-For": visitor})


def test_guards_are_off_by_default(scans: dict[str, Any]) -> None:
    get_settings.cache_clear()
    assert get_settings().scan_cache_seconds == 0
    assert get_settings().scans_per_visitor_per_10_min == 0
    client = TestClient(app)
    for _ in range(25):
        resp = _ingest(client, "https://wildmeadow.test")
        assert resp.status_code == 200
        assert "X-Muse-Scan-Cache" not in resp.headers
    assert len(scans["crawled"]) == 25


def test_cache_reuses_a_recent_crawl_of_the_same_website(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cache=900)
    client = TestClient(app)
    first = _ingest(client, "https://wildmeadow.test")
    # Same website: host case and a trailing slash do not matter; the business name is per request.
    second = client.post(
        "/api/v1/ingest-storefront",
        json={"business_name": "Another Seller", "website_url": "https://WildMeadow.test/"},
    )
    assert first.status_code == second.status_code == 200
    assert scans["crawled"] == ["https://wildmeadow.test"]
    assert second.headers["X-Muse-Scan-Cache"] == "1/1"
    assert second.json()["business_name"] == "Another Seller"
    assert second.json()["seller_context"].startswith("Another Seller.")
    assert second.json()["discovered_catalog_items"] == first.json()["discovered_catalog_items"]

    # A smaller page cap is answered from the bigger crawl (its first entries); a bigger cap is
    # crawled again; an expired entry is crawled again.
    assert first.json()["total_pages_crawled"] == 30
    smaller = _ingest(client, "https://wildmeadow.test", max_urls_per_source=20)
    assert smaller.headers["X-Muse-Scan-Cache"] == "1/1"
    assert smaller.json()["total_pages_crawled"] == 20
    assert len(scans["crawled"]) == 1
    bigger = _ingest(client, "https://wildmeadow.test", max_urls_per_source=40)
    assert bigger.json()["total_pages_crawled"] == 35
    assert len(scans["crawled"]) == 2
    scans["clock"] += 901
    _ingest(client, "https://wildmeadow.test")
    assert len(scans["crawled"]) == 3


def test_a_failed_crawl_is_never_cached(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cache=900)
    client = TestClient(app)
    scans["fail"].add("https://wildmeadow.test")
    failed = _ingest(client, "https://wildmeadow.test")
    assert failed.json()["channels"][0]["status"] == "vision_or_manual"
    scans["fail"].clear()
    fixed = _ingest(client, "https://wildmeadow.test")
    assert fixed.json()["channels"][0]["status"] == "fetched"
    assert len(scans["crawled"]) == 2


def test_both_public_scans_share_the_cache(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cache=900)
    client = TestClient(app)
    _ingest(client, "https://wildmeadow.test")  # page cap 30; the scan below asks for 25
    scan = client.post(
        "/api/v1/seller-memory/scan",
        json={"business_name": "Wild Meadow Prints", "website_url": "https://wildmeadow.test"},
    )
    assert scan.status_code == 200
    assert scan.headers["X-Muse-Scan-Cache"] == "1/1"
    assert scans["crawled"] == ["https://wildmeadow.test"]


def test_visitor_cap_refuses_before_any_crawl(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cap=3)
    client = TestClient(app)
    for n in range(3):
        assert _ingest(client, f"https://shop{n}.test").status_code == 200
    refused = _ingest(client, "https://shop3.test")
    assert refused.status_code == 429
    assert scans["crawled"] == ["https://shop0.test", "https://shop1.test", "https://shop2.test"]
    retry_after = int(refused.headers["Retry-After"])
    assert 0 < retry_after <= 600
    detail = refused.json()["detail"]
    assert "Try again in 10 minutes" in detail
    assert not any(word in detail for word in ("HTTP", "429", "rate limit", "—"))

    # Another visitor is not affected, and the public seller-memory scan counts the same way.
    assert _ingest(client, "https://shop3.test", visitor="198.51.100.7").status_code == 200
    blocked_scan = client.post(
        "/api/v1/seller-memory/scan",
        json={"website_url": "https://shop4.test"},
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    assert blocked_scan.status_code == 429

    # The window slides: once the first crawls are 10 minutes old, the visitor may scan again.
    scans["clock"] += 600
    assert _ingest(client, "https://shop5.test").status_code == 200


def test_a_request_is_refused_whole_when_it_needs_more_than_is_left(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cap=3)
    client = TestClient(app)
    assert _ingest(client, "https://shop0.test").status_code == 200
    # Three more sites with two left: nothing is crawled, no partial result.
    too_many = _ingest(
        client,
        "https://shop1.test",
        marketplace_urls=["https://shop2.test", "https://shop3.test"],
    )
    assert too_many.status_code == 429
    assert scans["crawled"] == ["https://shop0.test"]
    # Sites that refuse automated reading are never crawled, so they never count.
    blocked_only = _ingest(
        client,
        "https://shop1.test",
        marketplace_urls=["https://www.etsy.com/shop/wildmeadow"],
        social_urls=["@wildmeadow"],
    )
    assert blocked_only.status_code == 200
    # More sites than the whole cap can never pass, so the wait is the full window.
    fresh_visitor = _ingest(
        client,
        "https://a.test",
        visitor="198.51.100.9",
        marketplace_urls=["https://b.test", "https://c.test", "https://d.test"],
    )
    assert fresh_visitor.status_code == 429
    assert fresh_visitor.headers["Retry-After"] == "600"


def test_cached_websites_never_count_against_the_cap(
    scans: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(monkeypatch, cache=900, cap=1)
    client = TestClient(app)
    for _ in range(5):
        assert _ingest(client, "https://wildmeadow.test").status_code == 200
    assert scans["crawled"] == ["https://wildmeadow.test"]
    assert _ingest(client, "https://other.test").status_code == 429


def test_blocked_hosts_get_an_honest_note(scans: dict[str, Any]) -> None:
    get_settings.cache_clear()
    client = TestClient(app)
    resp = _ingest(client, "https://www.etsy.com/shop/wildmeadow")
    note = resp.json()["channels"][0]["note"]
    assert note == (
        "www.etsy.com does not allow automated reading, so Muse did not scan it. "
        "Add items from it yourself."
    )
    assert scans["crawled"] == []
