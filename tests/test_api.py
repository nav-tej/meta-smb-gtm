from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.api.bids import get_bid_advisor_service
from src.api.intel import get_competitor_intel_service
from src.api.main import app
from src.clients.meta import MetaClient
from src.config import Settings
from src.models.intel import CompetitorBrief, CompetitorIntelRequest
from src.services.bid_advisor import BidAdvisorService
from src.utils.sitemap import SitemapError
from tests.conftest import META_BASE_URL, build_campaign, chat_completion


class FakeIntelService:
    def __init__(self, brief: CompetitorBrief | None = None, error: Exception | None = None):
        self.brief, self.error = brief, error
        self.requests: list[CompetitorIntelRequest] = []

    async def analyze(self, request: CompetitorIntelRequest) -> CompetitorBrief:
        self.requests.append(request)
        if self.error:
            raise self.error
        assert self.brief is not None
        return self.brief


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def bid_payload(brief_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign": build_campaign().model_dump(mode="json"),
        "competitor_brief": brief_json,
        "seller_goal": "More holiday sales.",
    }


@pytest.fixture
def real_bid_service(test_settings: Settings) -> None:
    # Built per request so the httpx client lives on TestClient's event loop
    app.dependency_overrides[get_bid_advisor_service] = lambda: BidAdvisorService(
        meta_client=MetaClient(settings=test_settings, http_client=httpx.AsyncClient())
    )


def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_analyze_competitors(client: TestClient, competitor_brief: CompetitorBrief) -> None:
    fake = FakeIntelService(brief=competitor_brief)
    app.dependency_overrides[get_competitor_intel_service] = lambda: fake

    response = client.post(
        "/api/v1/analyze-competitors", json={"competitor_url": "example-prints.com"}
    )

    assert response.status_code == 200
    assert response.json()["competitor_domain"] == "example-prints.com"
    assert fake.requests[0].competitor_url == "example-prints.com"


def test_analyze_competitors_unreadable_site(client: TestClient) -> None:
    fake = FakeIntelService(error=SitemapError("No competitor URLs could be discovered"))
    app.dependency_overrides[get_competitor_intel_service] = lambda: fake

    response = client.post("/api/v1/analyze-competitors", json={"competitor_url": "nope.test"})

    assert response.status_code == 422
    assert "No competitor URLs" in response.json()["detail"]


def test_generate_ads_not_implemented_yet(client: TestClient, brief_json: dict[str, Any]) -> None:
    response = client.post(
        "/api/v1/generate-ads",
        json={"product": {"title": "Sunset Pier print"}, "competitor_brief": brief_json},
    )
    assert response.status_code == 501


@respx.mock
@pytest.mark.usefixtures("real_bid_service")
def test_bid_advice(
    client: TestClient, bid_payload: dict[str, Any], spark_bid_content: str
) -> None:
    respx.post(f"{META_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json=chat_completion(spark_bid_content))
    )

    response = client.post("/api/v1/bid-advice", json=bid_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["budget_reallocations"][0]["daily_amount"] == 5.8
    assert body["metrics"]["account_totals"]["spend"] == 696.0


@respx.mock
@pytest.mark.usefixtures("real_bid_service")
def test_bid_advice_meta_failure_is_502(client: TestClient, bid_payload: dict[str, Any]) -> None:
    respx.post(f"{META_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad key"}})
    )

    response = client.post("/api/v1/bid-advice", json=bid_payload)

    assert response.status_code == 502
    assert "status=401" in response.json()["detail"]


def test_bid_advice_rejects_empty_campaign(client: TestClient, bid_payload: dict[str, Any]) -> None:
    bid_payload["campaign"]["rows"] = []
    assert client.post("/api/v1/bid-advice", json=bid_payload).status_code == 422


def test_analyze_competitors_accepts_url_list(
    client: TestClient, competitor_brief: CompetitorBrief
) -> None:
    fake = FakeIntelService(brief=competitor_brief)
    app.dependency_overrides[get_competitor_intel_service] = lambda: fake

    response = client.post(
        "/api/v1/analyze-competitors",
        json={"urls": ["https://fineartamerica.com/featured/harvest-festival-jane-doe.html"]},
    )

    assert response.status_code == 200
    assert fake.requests[0].competitor_url is None
    assert len(fake.requests[0].pasted_urls) == 1


def test_analyze_competitors_requires_url_or_list(client: TestClient) -> None:
    assert client.post("/api/v1/analyze-competitors", json={}).status_code == 422
