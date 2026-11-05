"""Presenter live calls: need the key, check the result cache first, and cache hits cost nothing.

Offline: the bid service is a counting fake, so no Muse call or network request is made.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.bids import get_bid_advisor_service
from src.api.main import app
from src.config import get_settings
from src.models.bids import BidRecommendation
from src.services import demo, live_quota
from tests.conftest import build_campaign

DEMO_KEY = "test-demo-key"
LIVE = "/api/v1/bid-advice?live=true"


class CountingBidService:
    def __init__(self) -> None:
        self.calls = 0

    async def advise(self, request: Any) -> BidRecommendation:
        self.calls += 1
        return demo.demo_bid_recommendation().model_copy(update={"model": "live-call"})


@pytest.fixture
def gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, CountingBidService]]:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", DEMO_KEY)
    monkeypatch.setenv("LIVE_CALLS_PER_HOUR", "2")
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    live_quota.reset()
    service = CountingBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()
    live_quota.reset()
    get_settings.cache_clear()


@pytest.fixture
def bid_payload(brief_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign": build_campaign().model_dump(mode="json"),
        "competitor_brief": brief_json,
        "seller_goal": "More holiday sales.",
    }


def _payload(bid_payload: dict[str, Any], goal: str) -> dict[str, Any]:
    return {**bid_payload, "seller_goal": goal}


def test_saved_mode_never_calls_the_service(
    gated: tuple[TestClient, CountingBidService], bid_payload: dict[str, Any]
) -> None:
    client, service = gated
    response = client.post("/api/v1/bid-advice", json=bid_payload)
    assert response.status_code == 200
    assert "x-muse-cache" not in response.headers
    assert service.calls == 0 and live_quota.used() == 0


def test_live_needs_a_valid_key(
    gated: tuple[TestClient, CountingBidService], bid_payload: dict[str, Any]
) -> None:
    client, service = gated
    assert client.post(LIVE, json=bid_payload).status_code == 403
    assert client.post(LIVE, json=bid_payload, headers={"X-Demo-Key": "wrong"}).status_code == 403
    assert service.calls == 0 and live_quota.used() == 0


def test_cache_is_checked_first_and_hits_refund_the_live_slot(
    gated: tuple[TestClient, CountingBidService], bid_payload: dict[str, Any]
) -> None:
    client, service = gated
    headers = {"X-Demo-Key": DEMO_KEY}
    first = client.post(LIVE, json=bid_payload, headers=headers)
    assert first.status_code == 200 and first.headers["x-muse-cache"] == "miss"
    assert service.calls == 1 and live_quota.used() == 1
    for _ in range(5):
        repeat = client.post(LIVE, json=bid_payload, headers=headers)
        assert repeat.status_code == 200 and repeat.headers["x-muse-cache"] == "hit"
        assert repeat.json() == first.json()
    assert service.calls == 1, "cache hits must not call Muse"
    assert live_quota.used() == 1, "cache hits must not use up the hourly live cap"


def test_new_requests_still_hit_the_hourly_cap(
    gated: tuple[TestClient, CountingBidService], bid_payload: dict[str, Any]
) -> None:
    client, service = gated
    headers = {"X-Demo-Key": DEMO_KEY}
    assert (
        client.post(LIVE, json=_payload(bid_payload, "goal one"), headers=headers).status_code
        == 200
    )
    assert (
        client.post(LIVE, json=_payload(bid_payload, "goal two"), headers=headers).status_code
        == 200
    )
    capped = client.post(LIVE, json=_payload(bid_payload, "goal three"), headers=headers)
    assert capped.status_code == 429
    assert service.calls == 2
