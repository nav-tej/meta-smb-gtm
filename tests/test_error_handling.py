"""Users never see raw upstream errors or traces; failures fall back to cached/demo data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.intel import get_competitor_intel_service
from src.api.main import app, public_meta_error
from src.clients.comfyui import ComfyUIError
from src.clients.meta import MetaAPIError
from src.config import get_settings
from src.models.intel import CompetitorBrief
from src.services import result_cache

boom = APIRouter()


@boom.get("/__test/meta-internal")
async def _meta_internal() -> None:
    raise MetaAPIError(
        "Muse Spark output failed CompetitorBriefLLMOutput validation after retry: 3 errors"
    )


@boom.get("/__test/comfy")
async def _comfy() -> None:
    raise ComfyUIError("node 12 exploded at /private/path")


@boom.get("/__test/crash")
async def _crash() -> None:
    raise RuntimeError("secret internal state")


app.include_router(boom)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_internal_muse_errors_get_a_friendly_message(client: TestClient) -> None:
    response = client.get("/__test/meta-internal")
    assert response.status_code == 502
    assert "validation" not in response.text
    assert "try again" in response.json()["detail"]


def test_seller_facing_input_errors_pass_through() -> None:
    code, message = public_meta_error(
        MetaAPIError("Use a WAV voice note no longer than two minutes.")
    )
    assert code == 422 and message.startswith("Use a WAV")
    code, message = public_meta_error(MetaAPIError("META_MODEL_API_KEY is missing. Set it"))
    assert code == 503 and "KEY" not in message


def test_comfy_and_unexpected_errors_hide_details(client: TestClient) -> None:
    comfy = client.get("/__test/comfy")
    assert comfy.status_code == 502 and "/private/path" not in comfy.text
    crash = client.get("/__test/crash")
    assert crash.status_code == 500
    assert "secret internal state" not in crash.text
    assert "Traceback" not in crash.text
    assert crash.json()["code"] == "server_error"


def test_validation_errors_are_summarized(client: TestClient) -> None:
    response = client.post("/api/v1/bid-advice", json={"campaign": "nope"})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str) and body["code"] == "invalid_request"
    assert "campaign" in body["fields"]


class FailingIntel:
    async def analyze(self, request: Any) -> CompetitorBrief:
        raise MetaAPIError("Meta Model API transport failure: ConnectTimeout")


def test_live_analysis_failure_serves_the_stale_cached_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, competitor_brief: CompetitorBrief
) -> None:
    monkeypatch.setenv("RESULT_CACHE_ENABLED", "true")
    monkeypatch.setenv("RESULT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("RESULT_CACHE_TTL_SECONDS", "1")
    get_settings.cache_clear()
    from src.models.intel import CompetitorIntelRequest

    body = {"competitor_url": "https://shop.example", "seller_context": "Prints"}
    request = CompetitorIntelRequest.model_validate(body)
    result_cache.store(
        "analyze-competitors",
        request,
        competitor_brief,
        result_cache.TypeAdapter(CompetitorBrief),
    )
    path = next((tmp_path / "cache").glob("*.json"))
    path.write_text(path.read_text().replace('"stored_at":', '"stored_at":1,"old":'))
    app.dependency_overrides[get_competitor_intel_service] = FailingIntel
    try:
        response = TestClient(app).post("/api/v1/analyze-competitors?live=true", json=body)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["x-muse-cache"] == "stale"
    assert response.headers["x-muse-fallback"] == "stale-cache"
    assert response.json()["summary"] == competitor_brief.summary


def test_live_analysis_failure_without_cache_serves_the_saved_demo(
    competitor_brief: CompetitorBrief,
) -> None:
    app.dependency_overrides[get_competitor_intel_service] = FailingIntel
    try:
        response = TestClient(app).post(
            "/api/v1/analyze-competitors?live=true",
            json={"competitor_url": "https://www.sikhiart.com", "seller_context": "Prints"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["x-muse-fallback"] == "demo"
    assert "ConnectTimeout" not in response.text
