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
    # Same inputs: a refresh keeps today's brief instead of regenerating it.
    assert refreshed.headers["x-muse-cache"] == "hit"
    assert refreshed.headers["x-muse-brief"] == "unchanged"
    assert first.json()["generated_at"] == second.json()["generated_at"]


def test_signed_in_seller_gets_the_sample_brief_unless_they_ask_for_their_own(
    cache_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seller with a finished setup who opens the sample on /today must see the sample brief.

    The route used to pass every signed-in account to the brief, which then built the account
    stub (their competitors marked "monitored", "Feature a collection from <shop>") and /today
    showed it inside the sample's frame.
    """
    from src.api import daily_brief as daily_brief_api
    from src.services import daily_brief as daily_brief_service
    from src.services.accounts import AccountSession

    session = AccountSession(
        user_id="u-brief",
        email="owner@northstar.example",
        email_verified=True,
        access_token="offline",
        session_id=None,
    )

    async def signed_in(*args: object, **kwargs: object) -> AccountSession:
        return session

    async def workspace(*args: object, **kwargs: object) -> dict[str, object]:
        onboarding = {
            "business_name": "North Star Advisory",
            "competitors": [{"name": "Rival Advisory", "url": "https://rival.example/"}],
        }
        return {"document": {"onboarding": onboarding}}

    monkeypatch.setattr(daily_brief_api, "resolve_account", signed_in)
    monkeypatch.setattr(daily_brief_service, "load_workspace", workspace)
    client = TestClient(app)

    sample = client.get("/api/v1/daily-brief").json()
    assert not sample["inputs"].startswith("account:"), sample["inputs"]
    text = json.dumps(sample)
    assert "North Star Advisory" not in text and "Rival Advisory" not in text

    # Finished setup now builds a real own brief with watched competitors.
    async def completed_workspace(*args: object, **kwargs: object) -> dict[str, object]:
        result = await workspace()
        result["document"]["onboarding"]["completed_at"] = "2026-11-21T12:00:00Z"
        return result

    monkeypatch.setattr(daily_brief_service, "load_workspace", completed_workspace)
    own_response = client.get("/api/v1/daily-brief?workspace=own")
    assert own_response.status_code == 200
    own = own_response.json()
    assert own["business_name"] == "North Star Advisory"
    assert own["items"][0]["name"] == "Rival Advisory"
    assert own["items"][0]["status"] == "unchecked"
    assert own["move"]["recommendation"]["id"]
    assert client.get("/api/v1/daily-brief?workspace=other").status_code == 422
