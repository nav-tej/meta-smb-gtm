"""Account runs: only a new Muse result counts; failures, cache hits and fallbacks are given back.

Offline: the account, the accounting RPCs and the bid service are fakes.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import demo as demo_api
from src.api.bids import get_bid_advisor_service
from src.api.main import app
from src.clients.meta import MetaAPIError
from src.config import get_settings
from src.models.bids import BidRecommendation
from src.services import accounts, demo, usage_meter
from src.services.accounts import AccountSession
from tests.conftest import build_campaign

LIVE = "/api/v1/bid-advice?live=true"
OPERATION = "33333333-3333-3333-3333-333333333333"


class FakeBidService:
    def __init__(self) -> None:
        self.mode = "ok"
        self.calls = 0

    async def advise(self, request: Any) -> BidRecommendation:
        from src.clients.meta import _note_provider_call

        self.calls += 1
        _note_provider_call("chat")
        if self.mode == "muse-down":
            raise MetaAPIError("Meta Model API error (status=503): upstream")
        if self.mode == "crash":
            raise RuntimeError("unexpected bug")
        return demo.demo_bid_recommendation().model_copy(update={"model": "live-call"})


@pytest.fixture
def harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, FakeBidService, list[str]]]:
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    finished: list[str] = []

    async def fake_resolve(request: Any, response: Any = None, require_verified: bool = False):
        return AccountSession("11111111-1111-1111-1111-111111111111", "a@b.co", True, "t", None)

    async def fake_authorize(*args: Any, **kwargs: Any) -> str:
        return OPERATION

    async def fake_finish(status: str = "completed", *, operation_id: str | None = None) -> None:
        assert operation_id == OPERATION
        finished.append(status)

    monkeypatch.setattr(accounts, "resolve_account", fake_resolve)
    monkeypatch.setattr(usage_meter, "authorize_operation", fake_authorize)
    monkeypatch.setattr(usage_meter, "finish_operation", fake_finish)
    service = FakeBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: service
    yield (
        TestClient(app, base_url="https://testserver", raise_server_exceptions=False),
        service,
        finished,
    )
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def payload(brief_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign": build_campaign().model_dump(mode="json"),
        "competitor_brief": brief_json,
        "seller_goal": "More holiday sales.",
    }


def test_a_new_result_counts_as_a_run(harness: Any, payload: dict[str, Any]) -> None:
    client, service, finished = harness
    assert client.post(LIVE, json=payload).status_code == 200
    assert finished == ["completed"] and service.calls == 1


def test_a_repeat_from_the_cache_is_given_back(harness: Any, payload: dict[str, Any]) -> None:
    client, service, finished = harness
    client.post(LIVE, json=payload)
    repeat = client.post(LIVE, json=payload)
    assert repeat.headers["x-muse-cache"] == "hit"
    assert finished == ["completed", "refunded"] and service.calls == 1


def test_muse_outage_serves_a_labelled_fallback_and_gives_the_run_back(
    harness: Any, payload: dict[str, Any]
) -> None:
    client, service, finished = harness
    service.mode = "muse-down"
    response = client.post(LIVE, json=payload)
    assert response.status_code == 200
    assert response.headers.get("x-muse-fallback")  # the browser labels it as a saved result
    assert finished == ["refunded"]


def test_an_unexpected_error_marks_the_run_failed(harness: Any, payload: dict[str, Any]) -> None:
    client, service, finished = harness
    service.mode = "crash"
    assert client.post(LIVE, json=payload).status_code == 500
    assert finished == ["failed"]


def test_expired_session_is_rejected_before_any_run_or_muse_call(
    harness: Any, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException

    client, service, finished = harness

    async def expired(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(401, "Sign in again to continue.")

    monkeypatch.setattr(accounts, "resolve_account", expired)
    response = client.post(LIVE, json=payload)
    assert response.status_code == 401
    assert finished == [] and service.calls == 0


def test_run_outcome_rules() -> None:
    assert demo_api.run_outcome({"calls": ["chat"], "fallbacks": [], "hits": []}) == "completed"
    assert demo_api.run_outcome({"calls": [], "fallbacks": [], "hits": ["chat"]}) == "refunded"
    assert demo_api.run_outcome({"calls": ["c"], "fallbacks": ["c"], "hits": []}) == "refunded"
    # A cache hit plus a new billed call in the same run still delivered something new.
    assert demo_api.run_outcome({"calls": ["c"], "fallbacks": [], "hits": ["c"]}) == "completed"


def test_browser_handles_expiry_fallbacks_and_refunds_for_every_live_call() -> None:
    script = (Path(__file__).resolve().parents[1] / "src/api/static/account.js").read_text()
    assert "window.fetch = async (input, init)" in script
    assert "Your session ended before Muse started, so no run was used." in script
    assert "Live Muse was unavailable, so saved results are shown. No run was used." in script
    assert "refresh().catch" in script
