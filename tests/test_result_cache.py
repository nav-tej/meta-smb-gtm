"""Result cache for live Muse calls and snapshot-backed competitor briefs. Offline only."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from src.api.intel import get_competitor_intel_service
from src.api.main import app
from src.config import get_settings
from src.models.intel import CompetitorBrief, CompetitorIntelRequest
from src.services import result_cache
from src.services.demo import demo_competitor_brief_for, snapshot_competitor_brief


@pytest.fixture
def cache_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    yield tmp_path / "cache"
    get_settings.cache_clear()


class Counter:
    def __init__(self, value: Any) -> None:
        self.value, self.calls = value, 0

    async def __call__(self) -> Any:
        self.calls += 1
        return self.value


async def test_miss_then_hit(cache_on: Path, competitor_brief: CompetitorBrief) -> None:
    produce = Counter(competitor_brief)
    payload = {"competitor_url": "https://x.example"}
    first, second = Response(), Response()
    a = await result_cache.cached("ns", payload, CompetitorBrief, produce, first)
    b = await result_cache.cached("ns", payload, CompetitorBrief, produce, second)
    assert produce.calls == 1
    assert a == b
    assert (first.headers["X-Muse-Cache"], second.headers["X-Muse-Cache"]) == ("miss", "hit")
    assert len(list(cache_on.glob("ns-*.json"))) == 1  # noqa: ASYNC240


async def test_different_requests_do_not_collide(
    cache_on: Path, competitor_brief: CompetitorBrief
) -> None:
    produce = Counter(competitor_brief)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    await result_cache.cached("ns", {"u": 2}, CompetitorBrief, produce)
    await result_cache.cached("other", {"u": 1}, CompetitorBrief, produce)
    assert produce.calls == 3


async def test_expired_entries_are_ignored(
    cache_on: Path, competitor_brief: CompetitorBrief, monkeypatch: pytest.MonkeyPatch
) -> None:
    produce = Counter(competitor_brief)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    real_time = time.time
    monkeypatch.setattr(result_cache.time, "time", lambda: real_time() + 86400 + 5)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    assert produce.calls == 2


async def test_refresh_skips_read_but_stores(
    cache_on: Path, competitor_brief: CompetitorBrief
) -> None:
    produce = Counter(competitor_brief)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce, refresh=True)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    assert produce.calls == 2


async def test_corrupt_entry_is_a_miss(cache_on: Path, competitor_brief: CompetitorBrief) -> None:
    produce = Counter(competitor_brief)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    entry = next(cache_on.glob("ns-*.json"))  # noqa: ASYNC240
    entry.write_text(json.dumps({"stored_at": time.time(), "value": {"not": "a brief"}}))
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    assert produce.calls == 2


async def test_disabled_cache_always_calls(competitor_brief: CompetitorBrief) -> None:
    produce = Counter(competitor_brief)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce)
    assert produce.calls == 2


async def test_unwritable_cache_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, competitor_brief: CompetitorBrief
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(blocker / "cache"))
    get_settings.cache_clear()
    produce = Counter(competitor_brief)
    assert await result_cache.cached("ns", {"u": 1}, CompetitorBrief, produce) == competitor_brief
    get_settings.cache_clear()


class CountingIntelService:
    def __init__(self, brief: CompetitorBrief) -> None:
        self.brief, self.calls = brief, 0

    async def analyze(self, request: CompetitorIntelRequest) -> CompetitorBrief:
        self.calls += 1
        return self.brief


def test_live_route_reuses_cached_result(cache_on: Path, competitor_brief: CompetitorBrief) -> None:
    service = CountingIntelService(competitor_brief)
    app.dependency_overrides[get_competitor_intel_service] = lambda: service
    try:
        client = TestClient(app)
        body = {"competitor_url": "https://www.sikhiart.com"}
        first = client.post("/api/v1/analyze-competitors", json=body)
        second = client.post("/api/v1/analyze-competitors", json=body)
    finally:
        app.dependency_overrides.clear()
    assert first.status_code == second.status_code == 200
    assert (first.headers["x-muse-cache"], second.headers["x-muse-cache"]) == ("miss", "hit")
    assert service.calls == 1
    assert first.json() == second.json()


def test_cache_files_never_contain_the_api_key(
    cache_on: Path, competitor_brief: CompetitorBrief, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", "test-key-should-never-be-cached")
    get_settings.cache_clear()
    service = CountingIntelService(competitor_brief)
    app.dependency_overrides[get_competitor_intel_service] = lambda: service
    try:
        TestClient(app).post(
            "/api/v1/analyze-competitors", json={"competitor_url": "https://a.example"}
        )
    finally:
        app.dependency_overrides.clear()
    for entry in cache_on.glob("*.json"):
        assert "test-key-should-never-be-cached" not in entry.read_text()


@pytest.mark.parametrize(
    ("url", "name", "priced"),
    [
        (
            "https://fineartamerica.com/profiles/gurinderpreet-kaur/art/paintings",
            "Gurinderpreet Kaur",
            True,
        ),
        (
            "https://fineartamerica.com/profiles/manjot-singh-sachdeva/art/photographs",
            "Manjot Singh Sachdeva",
            True,
        ),
        ("https://www.saatchiart.com/gurdishpannu", "Gurdish Pannu", False),
    ],
)
def test_snapshot_briefs_are_labelled_and_priced(url: str, name: str, priced: bool) -> None:
    brief = snapshot_competitor_brief(url)
    assert brief is not None
    assert name in brief.summary
    assert "no Muse call" in brief.summary
    assert (brief.signals.usd_price_min is not None) is priced
    assert brief.actionable_insights


def test_unknown_competitor_falls_back_to_saved_sikhiart_brief() -> None:
    assert "sikhiart" in demo_competitor_brief_for("https://unknown.example").competitor_domain
    assert "sikhiart" in demo_competitor_brief_for(None).competitor_domain


def test_demo_mode_route_serves_the_matching_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    response = TestClient(app).post(
        "/api/v1/analyze-competitors",
        json={
            "competitor_url": "https://fineartamerica.com/profiles/manjot-singh-sachdeva/art/photographs"
        },
    )
    get_settings.cache_clear()
    assert response.status_code == 200
    assert "Manjot Singh Sachdeva" in response.json()["summary"]
