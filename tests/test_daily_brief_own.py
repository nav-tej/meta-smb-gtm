"""Own briefs use one private workspace read, no shared evidence and no model calls."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

from src.api import daily_brief as api
from src.api.main import app
from src.clients.meta import MetaClient
from src.config import get_settings
from src.services import daily_brief as service
from src.services.accounts import AccountSession

NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)
OWN_URL = "/api/v1/daily-brief?workspace=own"
# Canonical full JSON from 740d1fe:src/services/daily_brief.py, executed in an isolated
# module with NOW, empty live summaries/monitor, and the unchanged saved sample files.
SAMPLE_SHA256 = "0effdbdc3d0017f98f8e86f7f1f50f8386d5824f3f0e1ac7b2a7d04ec8e78615"


def _document(owner: str, *, minutes: int = 120, business_type: str = "products") -> dict[str, Any]:
    return {
        "onboarding": {
            "business_name": f"{owner} Studio",
            "business_type": business_type,
            "completed_at": "2026-11-20T12:00:00Z",
            "competitors": [
                {"name": f"{owner} Rival {n}", "url": f"https://{owner.lower()}-{n}.example"}
                for n in (1, 2)
            ],
        },
        "preferences": {
            "goal": "Grow visits",
            "access": {"minutes_per_week": minutes, "channels": ["instagram", "website"]},
        },
        "outcomes": [],
    }


@pytest.fixture
def offline(
    _never_use_real_meta_key: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Mock]:
    # conftest defaults to non-demo; explicitly restore this assignment's safety settings.
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    construction = Mock(side_effect=AssertionError("Daily briefs must not construct Muse"))
    monkeypatch.setattr(MetaClient, "__init__", construction)

    def no_network(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Daily brief attempted external HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    assert get_settings().demo_mode
    yield construction
    construction.assert_not_called()
    get_settings.cache_clear()


@pytest.fixture
def private_api(offline: Mock, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    stores = {owner: _document(owner) for owner in ("Alpha", "Beta")}
    sessions = {
        owner: AccountSession(
            user_id=owner,
            email=f"{owner.lower()}@example.test",
            email_verified=True,
            access_token="offline",
            session_id=None,
        )
        for owner in stores
    }

    async def resolve(
        request: Request, response: Response, require_verified: bool = False
    ) -> AccountSession | None:
        return sessions.get(request.headers.get("X-Test-Account", ""))

    async def load(account: AccountSession) -> dict[str, Any]:
        return {"document": deepcopy(stores[account.user_id]), "owner_id": account.user_id}

    loader = AsyncMock(side_effect=load)
    monkeypatch.setattr(api, "resolve_account", resolve)
    monkeypatch.setattr(service, "load_workspace", loader)
    return SimpleNamespace(client=TestClient(app), stores=stores, loader=loader, muse=offline)


@pytest.fixture
def forbid_shared(monkeypatch: pytest.MonkeyPatch) -> list[Mock]:
    guards = []
    for module, names in (
        (
            service,
            (
                "_fresh_live_summaries",
                "demo_competitor_brief",
                "snapshot_competitor_brief",
                "_trends",
            ),
        ),
        (service.competitor_monitor, ("load_changelog", "changes_since")),
        (api.durable_state, ("hydrate_monitor",)),
        (service.result_cache, ("load", "store", "cached", "get_raw", "put_raw", "cache_dir")),
    ):
        for name in names:
            # fail() is not swallowed by the sample builder's broad fallback handlers.
            guard = Mock(side_effect=lambda *a, **kw: pytest.fail("Own brief read shared data"))
            monkeypatch.setattr(module, name, guard)
            guards.append(guard)
    return guards


def _get(
    harness: SimpleNamespace, owner: str = "Alpha", *, refresh: bool = False
) -> httpx.Response:
    return harness.client.get(
        OWN_URL + ("&refresh=true" if refresh else ""), headers={"X-Test-Account": owner}
    )


def test_signed_out_is_401_without_workspace_read(private_api: SimpleNamespace) -> None:
    response = private_api.client.get(OWN_URL)
    assert response.status_code == 401
    assert "no-store" in response.headers["cache-control"]
    private_api.loader.assert_not_awaited()


@pytest.mark.parametrize("onboarding", [None, {}, {"business_name": "Alpha Studio"}])
def test_unfinished_setup_is_409(
    private_api: SimpleNamespace, onboarding: dict[str, Any] | None
) -> None:
    private_api.stores["Alpha"]["onboarding"] = onboarding
    response = _get(private_api)
    assert response.status_code == 409
    assert response.json() == {"detail": "Finish setup first"}
    assert "no-store" in response.headers["cache-control"]
    private_api.loader.assert_awaited_once()


def test_two_watched_businesses_return_private_200(
    private_api: SimpleNamespace, forbid_shared: list[Mock]
) -> None:
    response = _get(private_api)
    assert response.status_code == 200
    assert "private" in response.headers["cache-control"]
    assert "no-store" in response.headers["cache-control"]
    brief = response.json()
    assert brief["business_name"] == "Alpha Studio"
    assert [item["name"] for item in brief["items"]] == ["Alpha Rival 1", "Alpha Rival 2"]
    assert all(item["status"] == "unchecked" for item in brief["items"])
    assert all("Not checked yet" in item["note"] for item in brief["items"])
    assert 1 <= len(brief["action_items"]) <= 3
    assert brief["focus"] == brief["move"] == brief["action_items"][0]
    assert all("workspace=own" in move["href"] for move in brief["action_items"])
    assert brief["overnight_changes"] == []
    assert "does not check" in brief["overnight_note"]
    assert brief["trends"] == [] and brief["fresh_analyses"] == 0
    assert brief["outcomes"] == [] and "log a result" in brief["results_note"]
    private_api.loader.assert_awaited_once()
    for guard in forbid_shared:
        guard.assert_not_called()


@pytest.mark.parametrize("minutes, over_budget", [(5, True), (120, False)])
def test_services_copy_and_budget(
    private_api: SimpleNamespace, minutes: int, over_budget: bool
) -> None:
    private_api.stores["Alpha"] = _document("Alpha", minutes=minutes, business_type="services")
    response = _get(private_api)
    assert response.status_code == 200
    brief = response.json()
    assert not re.search(
        r"\b(shop|shops|collection|collections|catalog)\b", json.dumps(brief).lower()
    )
    assert brief["action_items"]
    for move in brief["action_items"]:
        assert move["over_budget"] is over_budget
        assert move["recommendation"]["over_budget"] is over_budget
        assert (move["recommendation"]["estimated_minutes"] > minutes) is over_budget
        if over_budget:
            assert "more than your 5 minutes" in move["reason"]


def test_account_a_b_a_never_share_watchlist_or_results(private_api: SimpleNamespace) -> None:
    for owner in ("Alpha", "Beta"):
        private_api.stores[owner]["outcomes"] = [
            {
                "id": f"{owner}-result",
                "title": f"{owner} private result",
                "revenue": 37,
                "date": "2026-11-20",
                "created_at": "2026-11-20T12:00:00Z",
            }
        ]
    for owner, other in (("Alpha", "Beta"), ("Beta", "Alpha"), ("Alpha", "Beta")):
        response = _get(private_api, owner)
        assert response.status_code == 200
        brief = response.json()
        assert brief["business_name"] == f"{owner} Studio"
        assert [result["id"] for result in brief["outcomes"]] == [f"{owner}-result"]
        assert brief["outcomes"][0]["revenue"] == 37
        assert other not in response.text
        assert all(item["name"].startswith(owner) for item in brief["items"])
    assert private_api.loader.await_count == 3


def test_seeded_private_live_analysis_never_enters_own_brief(private_api: SimpleNamespace) -> None:
    cache = service.result_cache.cache_dir()
    cache.mkdir(parents=True)
    path = cache / "analyze-competitors-private.json"
    private_summary = "Beta confidential pricing strategy for this competitor"
    path.write_text(
        json.dumps(
            {
                "stored_at": time.time(),
                "value": {"competitor_url": "https://alpha-1.example", "summary": private_summary},
            }
        )
    )
    original = path.read_bytes()
    # Prove the seed qualifies as fresh evidence rather than accidentally testing a stale file.
    assert service._fresh_live_summaries()[0][1] == private_summary
    response = _get(private_api)
    assert response.status_code == 200
    assert private_summary not in response.text
    assert response.json()["fresh_analyses"] == 0
    assert response.json()["items"][0]["status"] == "unchecked"
    assert list(cache.iterdir()) == [path]
    assert path.read_bytes() == original


@pytest.mark.parametrize("refresh", [False, True])
def test_each_request_reads_once_and_uses_latest_preferences(
    private_api: SimpleNamespace, forbid_shared: list[Mock], refresh: bool
) -> None:
    first = _get(private_api)
    assert first.status_code == 200
    private_api.loader.assert_awaited_once()
    assert first.json()["move"]["over_budget"] is False
    doc = private_api.stores["Alpha"]
    doc["preferences"]["access"] = {"minutes_per_week": 5, "channels": ["facebook"]}
    doc["preferences"]["competitor_entries"] = [
        {"name": "Latest Rival", "url": "https://latest.example", "selected": True},
        {"name": "Paused Rival", "url": "https://paused.example", "selected": False},
    ]
    second = _get(private_api, refresh=refresh)
    assert second.status_code == 200
    assert private_api.loader.await_count == 2
    brief = second.json()
    assert [item["name"] for item in brief["items"]] == ["Latest Rival"]
    assert brief["move"]["over_budget"] is True
    assert brief["move"]["recommendation"]["channel"] == "facebook"
    assert brief["move"] != first.json()["move"]
    doc["dismiss_signals"] = [{"reason": "wrong_channel", "channel": "facebook"}]
    third = _get(private_api, refresh=refresh)
    assert third.status_code == 200
    assert private_api.loader.await_count == 3
    assert third.json()["action_items"] == []
    for guard in forbid_shared:
        guard.assert_not_called()


def test_sample_api_json_matches_740d1fe_at_fixed_date(
    offline: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return NOW

    monkeypatch.setattr(service, "datetime", FixedDatetime)
    monkeypatch.setattr(service, "_fresh_live_summaries", lambda: [])
    monkeypatch.setattr(
        service.competitor_monitor,
        "load_changelog",
        lambda: SimpleNamespace(runs=[], last_checked_at=None),
    )
    monkeypatch.setattr(service.competitor_monitor, "changes_since", lambda *args: [])
    response = TestClient(app).get("/api/v1/daily-brief?workspace=sample")
    assert response.status_code == 200
    canonical = json.dumps(response.json(), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == SAMPLE_SHA256
