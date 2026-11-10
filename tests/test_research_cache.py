"""Tests for Track E: Content-addressed research cache and migration file."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.api.main import app
from src.config import Settings, get_settings
from src.services.accounts import AccountSession
from src.services.research_cache import (
    NAMESPACE_AD_PREVIEWS,
    NAMESPACE_COMPETITOR_CRAWL,
    NAMESPACE_DAILY_BRIEF,
    cached_research,
    compute_research_cache_key,
    set_research_cache_dir,
)


class MockResult(BaseModel):
    summary: str
    items: list[str]


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path: Path) -> None:
    cache_dir = tmp_path / "research_cache"
    set_research_cache_dir(cache_dir)


# ---------------------------------------------------------------------------
# 1. Cache key computation
# ---------------------------------------------------------------------------


def test_cache_key_deterministic_and_normalized() -> None:
    """Keys are 64-char hex SHA-256 digests and sort URL inputs."""
    k1 = compute_research_cache_key(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_123",
        ["https://store-b.com", "https://store-a.com"],
    )
    k2 = compute_research_cache_key(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_123",
        ["https://store-a.com", "https://store-b.com"],
    )
    assert len(k1) == 64
    assert k1 == k2

    # Different account ID changes key
    k3 = compute_research_cache_key(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_456",
        ["https://store-a.com", "https://store-b.com"],
    )
    assert k1 != k3

    # Different prompt version changes key
    k4 = compute_research_cache_key(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_123",
        ["https://store-a.com", "https://store-b.com"],
        prompt_version="v2",
    )
    assert k1 != k4


# ---------------------------------------------------------------------------
# 2. TTL behavior across namespaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_competitor_crawl_ttl_7_days() -> None:
    """Competitor crawl cache expires after 7 days."""
    t0 = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
    calls = 0

    async def produce() -> MockResult:
        nonlocal calls
        calls += 1
        return MockResult(summary="Competitor Crawl", items=["item1"])

    urls = "https://competitor.test"

    # Day 0: Initial run (miss)
    res1, hit1, label1 = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_1",
        urls,
        MockResult,
        produce,
        now=t0,
    )
    assert calls == 1
    assert hit1 is False
    assert "Last checked Nov 10 · Refresh (1 run)" in label1

    # Day 6: Within 7-day TTL (hit, 0 calls)
    t6 = t0 + timedelta(days=6)
    res2, hit2, label2 = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_1",
        urls,
        MockResult,
        produce,
        now=t6,
    )
    assert calls == 1
    assert hit2 is True
    assert res2 == res1
    assert "Last checked Nov 10 · Refresh (1 run)" in label2

    # Day 8: Past 7-day TTL (expired -> miss, producer runs)
    t8 = t0 + timedelta(days=8)
    res3, hit3, label3 = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL,
        "user_1",
        urls,
        MockResult,
        produce,
        now=t8,
    )
    assert calls == 2
    assert hit3 is False
    assert "Last checked Nov 18 · Refresh (1 run)" in label3


@pytest.mark.asyncio
async def test_daily_brief_ttl_24_hours() -> None:
    """Daily brief cache expires after 24 hours."""
    t0 = datetime(2026, 11, 10, 8, 0, 0, tzinfo=UTC)
    calls = 0

    async def produce() -> MockResult:
        nonlocal calls
        calls += 1
        return MockResult(summary="Daily Brief", items=["brief1"])

    urls = "https://shop.test"

    # Hour 0: miss
    _, hit0, _ = await cached_research(
        NAMESPACE_DAILY_BRIEF, "user_1", urls, MockResult, produce, now=t0
    )
    assert calls == 1
    assert hit0 is False

    # Hour 23: hit (0 runs)
    t23 = t0 + timedelta(hours=23)
    _, hit23, _ = await cached_research(
        NAMESPACE_DAILY_BRIEF, "user_1", urls, MockResult, produce, now=t23
    )
    assert calls == 1
    assert hit23 is True

    # Hour 25: expired
    t25 = t0 + timedelta(hours=25)
    _, hit25, _ = await cached_research(
        NAMESPACE_DAILY_BRIEF, "user_1", urls, MockResult, produce, now=t25
    )
    assert calls == 2
    assert hit25 is False


@pytest.mark.asyncio
async def test_ad_previews_no_expiry() -> None:
    """Ad previews have no expiration TTL."""
    t0 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)
    calls = 0

    async def produce() -> MockResult:
        nonlocal calls
        calls += 1
        return MockResult(summary="Ad Preview", items=["headline1"])

    urls = "https://shop.test/product-1"

    _, hit0, _ = await cached_research(
        NAMESPACE_AD_PREVIEWS, "user_1", urls, MockResult, produce, now=t0
    )
    assert calls == 1
    assert hit0 is False

    # 1 year later: still a valid cache hit
    t_future = t0 + timedelta(days=365)
    _, hit_future, label = await cached_research(
        NAMESPACE_AD_PREVIEWS, "user_1", urls, MockResult, produce, now=t_future
    )
    assert calls == 1
    assert hit_future is True
    assert "Refresh (1 run)" in label


# ---------------------------------------------------------------------------
# 3. Force refresh & migration file checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_refresh_charges_run() -> None:
    """When force_refresh=True, bypasses valid cache and executes producer."""
    calls = 0

    async def produce() -> MockResult:
        nonlocal calls
        calls += 1
        return MockResult(summary="Result", items=[str(calls)])

    urls = "https://shop.test"

    # Call 1: Miss
    r1, hit1, _ = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL, "user_1", urls, MockResult, produce
    )
    assert calls == 1
    assert hit1 is False

    # Call 2: Hit
    r2, hit2, _ = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL, "user_1", urls, MockResult, produce
    )
    assert calls == 1
    assert hit2 is True

    # Call 3: Forced refresh
    r3, hit3, _ = await cached_research(
        NAMESPACE_COMPETITOR_CRAWL, "user_1", urls, MockResult, produce, force_refresh=True
    )
    assert calls == 2
    assert hit3 is False
    assert r3.items == ["2"]


def test_research_cache_migration_files_exist() -> None:
    """Track E migration files exist and define the expected schema."""
    repo_root = Path(__file__).resolve().parents[1]
    migration = repo_root / "supabase" / "migrations" / "research_cache.sql"
    rollback = repo_root / "supabase" / "migrations" / "research_cache_rollback.sql"

    assert migration.is_file()
    assert rollback.is_file()

    sql = migration.read_text(encoding="utf-8")
    assert "create table if not exists muse_private.research_cache" in sql
    assert "cache_key text primary key" in sql
    assert "namespace text not null" in sql
    assert "response_json jsonb not null" in sql
    assert "idx_research_cache_namespace" in sql
    assert "enable row level security" in sql

    rb_sql = rollback.read_text(encoding="utf-8")
    assert "drop table if exists muse_private.research_cache" in rb_sql
    # Warning/Limitation: CASCADE destroys all cached rows and dependent relations permanently.
    assert "cascade" in rb_sql.lower()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_route_level_zero_debit_on_cache_hits(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Every route utilizing research cache spends zero runs on cache hits."""
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    # 1. /api/v1/daily-brief cache hit test
    resp1 = client.get("/api/v1/daily-brief")
    assert resp1.status_code == 200
    brief1 = resp1.json()
    assert "No new Muse call" in brief1["source"] or "0 runs spent" in brief1["source"]

    resp2 = client.get("/api/v1/daily-brief")
    assert resp2.status_code == 200
    assert resp2.headers.get("x-muse-cache") == "hit"
    brief2 = resp2.json()
    assert brief2["date"] == brief1["date"]
    assert "No new Muse call" in brief2["source"] or "0 runs spent" in brief2["source"]

    # 2. /api/v1/competitors/ads cache hit test with authenticated account
    settings_with_token = Settings(meta_ads_access_token="test_token_cache_route")
    app.dependency_overrides[get_settings] = lambda: settings_with_token

    fake_session = AccountSession(
        user_id="user_cache_route_1",
        email="artist@example.com",
        email_verified=True,
        access_token="tok",
        session_id="sess",
    )

    async def fake_resolve(*_a, **_kw):
        return fake_session

    monkeypatch.setattr("src.api.intel.resolve_account", fake_resolve)

    live_payload = {
        "data": [
            {
                "id": "99887766",
                "page_name": "Studio Cache Test",
                "ad_delivery_start_time": "2026-10-01T00:00:00+0000",
                "publisher_platforms": ["instagram"],
                "ad_creative_link_titles": ["Handmade Mugs"],
                "ad_creative_bodies": ["Wheel-thrown pottery"],
            }
        ]
    }
    mock_response = httpx.Response(
        status_code=200,
        content=json.dumps(live_payload).encode("utf-8"),
        request=httpx.Request("GET", "https://graph.facebook.com/v21.0/ads_archive"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        r1 = client.get("/api/v1/competitors/ads?query=Studio+Cache+Test")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["is_cached"] is False
        assert mock_get.call_count == 1

        r2 = client.get("/api/v1/competitors/ads?query=Studio+Cache+Test")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["is_cached"] is True
        # Zero external API calls on cache hit:
        assert mock_get.call_count == 1

    app.dependency_overrides.clear()


def test_per_account_cache_separation(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Prove that Account A and Account B querying the same resource have distinct cache entries."""
    settings_with_token = Settings(meta_ads_access_token="test_token_cache_sep")
    app.dependency_overrides[get_settings] = lambda: settings_with_token

    user_a = AccountSession(
        user_id="user_alpha_111",
        email="alpha@studio.test",
        email_verified=True,
        access_token="tok_a",
        session_id="sess_a",
    )
    user_b = AccountSession(
        user_id="user_beta_222",
        email="beta@studio.test",
        email_verified=True,
        access_token="tok_b",
        session_id="sess_b",
    )

    active_user = user_a

    async def dynamic_resolve(*_a, **_kw):
        return active_user

    monkeypatch.setattr("src.api.intel.resolve_account", dynamic_resolve)

    live_payload = {
        "data": [
            {
                "id": "77665544",
                "page_name": "Shared Competitor",
                "ad_delivery_start_time": "2026-10-15T00:00:00+0000",
                "publisher_platforms": ["instagram"],
                "ad_creative_link_titles": ["Archival Prints"],
                "ad_creative_bodies": ["Limited editions."],
            }
        ]
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(live_payload).encode("utf-8"),
        request=httpx.Request("GET", "https://graph.facebook.com/v21.0/ads_archive"),
    )

    with patch("httpx.AsyncClient.get", return_value=mock_resp) as mock_get:
        # 1. User A queries -> misses, fetches, stores in User A's account namespace
        active_user = user_a
        resp_a1 = client.get("/api/v1/competitors/ads?query=Shared+Competitor")
        assert resp_a1.status_code == 200
        assert resp_a1.json()["is_cached"] is False
        assert mock_get.call_count == 1

        # 2. User A queries again -> hits User A's cache (0 external fetches)
        resp_a2 = client.get("/api/v1/competitors/ads?query=Shared+Competitor")
        assert resp_a2.status_code == 200
        assert resp_a2.json()["is_cached"] is True
        assert mock_get.call_count == 1

        # 3. User B queries identical query -> MUST MISS (account cache separation)
        active_user = user_b
        resp_b1 = client.get("/api/v1/competitors/ads?query=Shared+Competitor")
        assert resp_b1.status_code == 200
        assert resp_b1.json()["is_cached"] is False
        assert mock_get.call_count == 2  # Proves separate fetch and isolated account cache!

        # 4. User B queries again -> hits User B's cache
        resp_b2 = client.get("/api/v1/competitors/ads?query=Shared+Competitor")
        assert resp_b2.status_code == 200
        assert resp_b2.json()["is_cached"] is True
        assert mock_get.call_count == 2

    app.dependency_overrides.clear()
