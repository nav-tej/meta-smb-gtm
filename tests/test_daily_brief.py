"""Daily growth brief: built from saved data and fresh cached analyses, cached per day."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.services.daily_brief import build_daily_brief


@pytest.fixture
def cache_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    yield tmp_path / "cache"
    get_settings.cache_clear()


def test_brief_covers_the_watchlist_from_saved_data() -> None:
    brief = build_daily_brief()
    assert [i.name for i in brief.items] == [
        "SikhiArt.com",
        "Gurinderpreet Kaur",
        "Manjot Singh Sachdeva",
        "Gurdish Pannu",
    ]
    assert brief.items[0].status == "new"
    assert all(i.status in {"new", "first"} for i in brief.items)
    assert "No new Muse call" in brief.source
    assert brief.move.href.startswith("/create")


def test_fresh_cached_analysis_is_surfaced(cache_on: Path) -> None:
    cache_on.mkdir(parents=True)
    entry = {
        "stored_at": time.time() - 3600 * 2,
        "value": {
            "competitor_url": "https://fineartamerica.com/profiles/manjot-singh-sachdeva",
            "summary": "Live summary text",
        },
    }
    (cache_on / "analyze-competitors-abc.json").write_text(json.dumps(entry))
    brief = build_daily_brief()
    manjot = next(i for i in brief.items if i.name == "Manjot Singh Sachdeva")
    assert manjot.status == "fresh"
    assert "Live summary text" in manjot.note
    assert brief.fresh_analyses == 1


def test_stale_cached_analysis_is_ignored(cache_on: Path) -> None:
    cache_on.mkdir(parents=True)
    entry = {
        "stored_at": time.time() - 86400 * 2,
        "value": {"competitor_url": "https://www.sikhiart.com", "summary": "Old"},
    }
    (cache_on / "analyze-competitors-old.json").write_text(json.dumps(entry))
    assert build_daily_brief().fresh_analyses == 0


def test_route_caches_the_brief_for_the_day(cache_on: Path) -> None:
    client = TestClient(app)
    first = client.get("/api/v1/daily-brief")
    second = client.get("/api/v1/daily-brief")
    refreshed = client.get("/api/v1/daily-brief?refresh=true")
    assert first.status_code == second.status_code == refreshed.status_code == 200
    assert first.headers["x-muse-cache"] == "miss"
    assert second.headers["x-muse-cache"] == "hit"
    assert refreshed.headers["x-muse-cache"] == "miss"
    assert first.json()["generated_at"] == second.json()["generated_at"]
