from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.content_plan import get_content_plan_service, router
from src.api.demo import _live_calls
from src.clients.meta import MetaAPIError, MetaClient
from src.config import get_settings
from src.models.content_plan import ContentPlanDraft, ContentPlanRequest
from src.services.content_plan import ContentPlanService, starter_plan


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def payload(**changes: object) -> dict:
    return {
        "product": {"title": "My original bowl", "description": "A small blue bowl."},
        "channels": ["instagram", "facebook"],
        **changes,
    }


def test_starter_reflects_current_item_and_never_calls_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ContentPlanService,
        "generate",
        AsyncMock(side_effect=AssertionError("No live call allowed")),
    )
    response = client.post("/api/v1/content-plan", json=payload())
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "starter"
    assert [post["day_offset"] for post in data["posts"]] == [0, 2, 4]
    assert "My original bowl" in data["posts"][0]["hook"]
    assert "Sarabjit" not in response.text and "$75" not in response.text
    assert data["insight"]["source"] == "not_connected"


@pytest.mark.parametrize(
    "channel,expected",
    [("instagram", "image"), ("facebook", "image"), ("x", "image"), ("tiktok", "video")],
)
def test_selected_channel_and_honest_formats(channel: str, expected: str) -> None:
    result = starter_plan(ContentPlanRequest.model_validate(payload(channels=[channel])))
    assert result.recommended_channel == channel
    assert result.recommended_format == expected
    assert {post.channel for post in result.posts} == {channel}
    if channel == "tiktok":
        assert all("no video has been generated" in post.visual_direction for post in result.posts)
    if channel == "x":
        assert result.posts[-1].format == "text"
        assert all(len(post.hook + post.caption + post.cta) < 230 for post in result.posts)


@pytest.mark.parametrize("body,use_live", [(payload(use_muse=True), False), (payload(), True)])
def test_ambiguous_live_flags_do_not_spend(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, body: dict, use_live: bool
) -> None:
    generate = AsyncMock(side_effect=AssertionError("No provider call allowed"))
    monkeypatch.setattr(ContentPlanService, "generate", generate)
    response = client.post("/api/v1/content-plan" + ("?live=true" if use_live else ""), json=body)
    assert response.status_code == 422
    generate.assert_not_called()


def test_guarded_live_requires_unlock(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "content-test-unlock")
    get_settings.cache_clear()
    generate = AsyncMock(side_effect=AssertionError("No provider call allowed"))
    monkeypatch.setattr(ContentPlanService, "generate", generate)
    response = client.post("/api/v1/content-plan?live=true", json=payload(use_muse=True))
    assert response.status_code == 403
    generate.assert_not_called()


def test_authorized_live_reaches_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_KEY", "content-test-unlock")
    get_settings.cache_clear()
    _live_calls.clear()
    result = starter_plan(ContentPlanRequest.model_validate(payload())).model_copy(
        update={"mode": "muse"}
    )
    service = AsyncMock(spec=ContentPlanService)
    service.generate.return_value = result
    client.app.dependency_overrides[get_content_plan_service] = lambda: service
    response = client.post(
        "/api/v1/content-plan?live=true",
        json=payload(use_muse=True),
        headers={"X-Demo-Key": "content-test-unlock"},
    )
    assert response.status_code == 200 and response.json()["mode"] == "muse"
    service.generate.assert_awaited_once()
    _live_calls.clear()


def test_performance_calculation_is_entered_data_not_connected_attribution() -> None:
    request = ContentPlanRequest.model_validate(
        payload(sales_goal=5, performance={"views": 100, "clicks": 20, "inquiries": 3, "sales": 2})
    )
    insight = starter_plan(request).insight
    assert insight.source == "user_entered"
    assert insight.click_through_rate_pct == 20
    assert insight.click_to_sale_rate_pct == 10
    assert insight.sales_remaining == 3
    assert "do not establish" in insight.summary
    zero = starter_plan(ContentPlanRequest.model_validate(payload(performance={}))).insight
    assert zero.click_through_rate_pct is None
    assert zero.click_to_sale_rate_pct is None


@pytest.mark.parametrize(
    "changes",
    [
        {"channels": []},
        {"channels": ["made-up-channel"]},
        {"performance": {"sales": -1}},
        {"product": {"title": " ", "destination_url": "javascript:alert(1)"}},
    ],
)
def test_invalid_inputs_rejected(client: TestClient, changes: dict) -> None:
    assert client.post("/api/v1/content-plan", json=payload(**changes)).status_code == 422


@pytest.mark.asyncio
async def test_muse_cannot_choose_unselected_channel() -> None:
    draft = starter_plan(ContentPlanRequest.model_validate(payload(channels=["facebook"])))
    client = AsyncMock(spec=MetaClient)
    client.chat_structured.return_value = ContentPlanDraft.model_validate(draft.model_dump())
    with pytest.raises(MetaAPIError, match="did not select"):
        await ContentPlanService(client).generate(
            ContentPlanRequest.model_validate(payload(channels=["instagram"]))
        )


@pytest.mark.asyncio
async def test_structured_muse_success_and_malformed_response(
    respx_mock: object, test_settings: object
) -> None:
    request = ContentPlanRequest.model_validate(payload(channels=["instagram"]))
    content = starter_plan(request).model_dump(
        include={"recommended_channel", "recommended_format", "reason", "posts"}
    )

    def completion(body: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "plan",
                "object": "chat.completion",
                "created": 0,
                "model": "muse-spark-1.3",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": body},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    route = respx_mock.post("https://api.meta.ai/v1/chat/completions")
    route.mock(return_value=completion(json.dumps(content)))
    service = ContentPlanService(MetaClient(settings=test_settings))
    result = await service.generate(request)
    assert result.mode == "muse"
    assert result.insight.source == "not_connected"
    route.mock(return_value=completion('{"posts": []}'))
    with pytest.raises(MetaAPIError):
        await service.generate(request)
