"""Demo mode: cached responses by default, keyed and rate-limited live calls."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.api.demo as demo_guard
from src.api.bids import get_bid_advisor_service
from src.api.main import app
from src.config import get_settings
from tests.conftest import build_campaign

DEMO_KEY = "test-demo-key"


@pytest.fixture
def demo_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", DEMO_KEY)
    monkeypatch.setenv("LIVE_CALLS_PER_HOUR", "2")
    get_settings.cache_clear()
    demo_guard._live_calls.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
    demo_guard._live_calls.clear()


class CountingBidService:
    def __init__(self) -> None:
        self.calls = 0

    async def advise(self, request: Any) -> Any:
        self.calls += 1
        from src.services.demo import demo_bid_recommendation

        return demo_bid_recommendation().model_copy(update={"model": "live-call"})


@pytest.fixture
def bid_payload(brief_json: dict[str, Any]) -> dict[str, Any]:
    return {"campaign": build_campaign().model_dump(mode="json"), "competitor_brief": brief_json}


def test_paid_endpoints_serve_saved_results_without_calling_muse(
    demo_client: TestClient, bid_payload: dict[str, Any], brief_json: dict[str, Any]
) -> None:
    service = CountingBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: service

    bid = demo_client.post("/api/v1/bid-advice", json=bid_payload)
    assert bid.status_code == 200
    assert bid.json()["model"] == "muse-spark-1.3"  # the saved live result
    assert service.calls == 0

    brief = demo_client.post("/api/v1/analyze-competitors", json={"competitor_url": "x.com"})
    assert brief.json()["competitor_domain"] == "www.sikhiart.com"

    product = {"title": "Golden Temple"}
    draft = demo_client.post(
        "/api/v1/generate-ads",
        json={"product": product, "competitor_brief": brief_json, "draft": True},
    )
    assert draft.json()["kind"] == "draft"
    rendered = demo_client.post(
        "/api/v1/generate-ads", json={"product": product, "brief": draft.json()}
    )
    creative = rendered.json()["creatives"][0]
    assert creative["image_path"].startswith("samples/")
    assert creative["produced_by"].startswith("demo-cache")

    voice = demo_client.post("/api/v1/transcribe-voice", json={"audio_base64": "AAAA"})
    assert voice.status_code == 403


def test_live_calls_need_the_key_and_are_capped(
    demo_client: TestClient, bid_payload: dict[str, Any]
) -> None:
    service = CountingBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: service
    url = "/api/v1/bid-advice?live=true"

    assert demo_client.post(url, json=bid_payload).status_code == 403
    bad = demo_client.post(url, json=bid_payload, headers={"X-Demo-Key": "wrong"})
    assert bad.status_code == 403
    assert service.calls == 0

    headers = {"X-Demo-Key": DEMO_KEY}
    for _ in range(2):
        ok = demo_client.post(url, json=bid_payload, headers=headers)
        assert ok.json()["model"] == "live-call"
    assert demo_client.post(url, json=bid_payload, headers=headers).status_code == 429
    assert service.calls == 2
