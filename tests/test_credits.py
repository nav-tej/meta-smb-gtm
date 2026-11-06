"""Server-side credits: balance checked before live calls, refunds, friendly errors (offline)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.bids import get_bid_advisor_service
from src.api.main import app
from src.clients.meta import MetaAPIError
from src.config import get_settings
from src.models.bids import BidRecommendation
from src.services import credits, demo, live_quota
from tests.conftest import build_campaign

LIVE = "/api/v1/bid-advice?live=true"
JSON = {"Content-Type": "application/json"}


class FakeBidService:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def advise(self, request: Any) -> BidRecommendation:
        from src.clients.meta import _note_provider_call

        self.calls += 1
        _note_provider_call("chat")  # stands in for the real billed Muse request
        if self.fail:
            raise MetaAPIError("Meta Model API error (status=500): upstream detail")
        return demo.demo_bid_recommendation().model_copy(update={"model": "live-call"})


@pytest.fixture
def bid_payload(brief_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign": build_campaign().model_dump(mode="json"),
        "competitor_brief": brief_json,
        "seller_goal": "More holiday sales.",
    }


@pytest.fixture
def service() -> Iterator[FakeBidService]:
    fake = FakeBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def _goal(payload: dict[str, Any], goal: str) -> dict[str, Any]:
    return {**payload, "seller_goal": goal}


# ---------- ledger ----------


def test_ledger_reserve_refund_add_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_CREDIT_BALANCE", "12")
    get_settings.cache_clear()
    holder = "anon:test"
    assert credits.balance(holder) == 3
    holds = [credits.reserve(holder) for _ in range(3)]
    with pytest.raises(credits.CreditsExhaustedError):
        credits.reserve(holder)
    credits.refund(holds[0], "test")
    credits.refund(holds[0], "test")  # refunds are idempotent
    assert credits.balance(holder) == 1
    assert credits.add(holder, 100, "top-up") == 12  # capped
    assert credits.summary(holder)["spent"] == 2


def test_cookie_value_is_hashed_never_stored() -> None:
    fresh = credits.holder_for(None)
    assert fresh.new_cookie and fresh.new_cookie not in fresh.id
    again = credits.holder_for(fresh.new_cookie)
    assert again.id == fresh.id and again.new_cookie is None
    assert credits.holder_for("bad value!").new_cookie is not None


def test_corrupt_ledger_fails_closed(service: FakeBidService, bid_payload: dict) -> None:
    directory = credits.ledger_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ledger.json").write_text("{not json")
    response = TestClient(app, base_url="https://testserver").post(LIVE, json=bid_payload)
    assert response.status_code == 503
    assert response.json()["code"] == "credits_unavailable"
    assert service.calls == 0


# ---------- routes ----------


def test_get_credits_sets_cookie_and_reports_balance() -> None:
    client = TestClient(app, base_url="https://testserver")
    first = client.get("/api/v1/credits")
    assert first.status_code == 200
    assert first.json()["balance"] == 3
    assert credits.COOKIE_NAME in first.cookies
    assert client.get("/api/credits").json()["balance"] == 3  # short alias, same browser


def test_spend_until_empty_then_friendly_402() -> None:
    client = TestClient(app, base_url="https://testserver")
    balances = [
        client.post("/api/v1/credits/spend", json={"label": "Analysis"}).json()["balance"]
        for _ in range(3)
    ]
    assert balances == [2, 1, 0]
    empty = client.post("/api/v1/credits/spend", json={"label": "Analysis"})
    assert empty.status_code == 402
    body = empty.json()
    assert body["code"] == "credits_exhausted"
    assert "out of runs" in body["detail"]
    assert "Traceback" not in empty.text


def test_spend_rejects_non_json_posts() -> None:
    client = TestClient(app, base_url="https://testserver")
    response = client.post(
        "/api/v1/credits/spend", content='{"label":"x"}', headers={"Content-Type": "text/plain"}
    )
    assert response.status_code in {415, 422}
    assert client.get("/api/v1/credits").json()["balance"] == 3


def test_demo_plan_adds_runs_but_custom_amount_needs_admin_when_hosted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOSTED_ENVIRONMENT", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "presenter-key")
    get_settings.cache_clear()
    client = TestClient(app, base_url="https://testserver")
    added = client.post("/api/v1/credits/add", json={"plan": "starter"})
    assert added.json()["balance"] == 13
    assert added.json()["persistent"] is False and added.json()["note"]
    assert client.post("/api/v1/credits/add", json={"amount": 50}).status_code == 403
    admin = client.post(
        "/api/v1/credits/add", json={"amount": 5}, headers={"X-Demo-Key": "presenter-key"}
    )
    assert admin.status_code == 200
    assert admin.json()["holder"] == "presenter"
    assert admin.json()["balance"] == get_settings().presenter_credits + 5


def test_accounts_mode_defers_to_the_account_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    get_settings.cache_clear()
    body = TestClient(app, base_url="https://testserver").get("/api/v1/credits").json()
    assert body["source"] == "account" and body["balance"] is None


# ---------- live gate ----------


def test_live_calls_spend_server_credits_and_stop_at_zero(
    service: FakeBidService, bid_payload: dict[str, Any]
) -> None:
    client = TestClient(app, base_url="https://testserver")
    for i in range(3):
        response = client.post(LIVE, json=_goal(bid_payload, f"goal {i}"))
        assert response.status_code == 200
        assert response.headers["x-muse-credits"] == str(2 - i)
    blocked = client.post(LIVE, json=_goal(bid_payload, "goal 4"))
    assert blocked.status_code == 402
    assert blocked.json()["code"] == "credits_exhausted"
    assert service.calls == 3  # balance was checked before the fourth (billed) call
    assert client.get("/api/v1/credits").json()["balance"] == 0


def test_cache_hit_refunds_the_credit(
    service: FakeBidService,
    bid_payload: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    client = TestClient(app, base_url="https://testserver")
    client.post(LIVE, json=bid_payload)
    repeat = client.post(LIVE, json=bid_payload)
    assert repeat.headers["x-muse-cache"] == "hit"
    assert service.calls == 1
    assert client.get("/api/v1/credits").json()["balance"] == 2


def test_failed_live_call_falls_back_and_refunds(bid_payload: dict[str, Any]) -> None:
    failing = FakeBidService(fail=True)
    app.dependency_overrides[get_bid_advisor_service] = lambda: failing
    try:
        client = TestClient(app, base_url="https://testserver")
        response = client.post(LIVE, json=bid_payload)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["x-muse-fallback"] == "demo"
    assert "upstream detail" not in response.text
    assert client.get("/api/v1/credits").json()["balance"] == 3


def test_presenter_key_uses_its_own_pool_and_the_hourly_cap(
    service: FakeBidService, bid_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "presenter-key")
    monkeypatch.setenv("PRESENTER_CREDITS", "1")
    get_settings.cache_clear()
    live_quota.reset()
    client = TestClient(app, base_url="https://testserver")
    headers = {"X-Demo-Key": "presenter-key"}
    assert client.post(LIVE, json=bid_payload, headers=headers).status_code == 200
    out = client.post(LIVE, json=_goal(bid_payload, "second"), headers=headers)
    assert out.status_code == 402
    assert live_quota.used() == 1  # the refused request handed its hourly slot back
    assert client.post(LIVE, json=bid_payload).status_code == 403  # no key: no live call
    live_quota.reset()


def test_disabled_credits_do_not_block(
    service: FakeBidService, bid_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CREDITS_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(app, base_url="https://testserver")
    for i in range(5):
        assert client.post(LIVE, json=_goal(bid_payload, f"g{i}")).status_code == 200
