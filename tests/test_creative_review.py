"""Two-phase ad creative flow: draft a reviewable brief, then render the edited brief."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.creative import get_ad_creative_service
from src.api.main import app
from src.clients.meta import MetaClient
from src.models.creative import (
    CreativeSet,
    EditableCreativeBrief,
    EditableCreativeVariant,
    GenerateAdsRequest,
    ProductInfo,
)
from src.models.intel import CompetitorBrief
from src.services.ad_creative import AdCreativeService
from tests.conftest import META_BASE_URL, chat_completion

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _angle(placement: str, n: int) -> dict[str, str]:
    return {
        "placement": placement,
        "target_audience": f"Audience {n}: Sikh families buying Gurpurab gifts",
        "scene_prompt": f"Scene {n}: warm living room wall",
        "headline": f"Headline {n}",
        "primary_text": f"Primary text {n}",
        "angle_rationale": "Competitor has nothing under $60",
    }


BRIEF_LLM = {
    "positioning_hook": "Hand-signed Sikh heritage prints",
    "preserve_product_note": "Keep the painting untouched.",
    "angles": [
        _angle("facebook_feed", 1),
        _angle("facebook_feed", 2),
        _angle("facebook_feed", 3),
        _angle("instagram_story", 4),
    ],
}


def _image_response() -> httpx.Response:
    return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG_1PX).decode()}]})


def _service(http_client: httpx.AsyncClient, tmp_path: Path) -> AdCreativeService:
    return AdCreativeService(
        meta_client=MetaClient(api_key="test-key", http_client=http_client),
        http_client=http_client,
        output_dir=tmp_path,
    )


def _draft_brief() -> EditableCreativeBrief:
    return EditableCreativeBrief(
        product_title="Golden Temple",
        positioning_hook="Heritage prints",
        variants=[
            EditableCreativeVariant(
                variant_id="v1",
                placement="facebook_feed",
                headline="Original headline",
                primary_text="Original text",
                image_prompt="Original scene",
            ),
            EditableCreativeVariant(
                variant_id="v2",
                placement="facebook_feed",
                target_audience="Collectors of Punjabi folk art",
                headline="Original headline 2",
                primary_text="Original text 2",
                image_prompt="Original scene 2",
            ),
        ],
    )


@respx.mock
async def test_draft_returns_editable_brief_without_generating_images(
    competitor_brief: CompetitorBrief, tmp_path: Path
) -> None:
    chat = respx.post(f"{META_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json=chat_completion(json.dumps(BRIEF_LLM)))
    )
    images = respx.post(f"{META_BASE_URL}/images/generations")

    async with httpx.AsyncClient() as http_client:
        draft = await _service(http_client, tmp_path).draft(
            GenerateAdsRequest(
                product=ProductInfo(title="Golden Temple"),
                competitor_brief=competitor_brief,
                placements=["facebook_feed"],
                variants_per_placement=2,
                draft=True,
            )
        )

    assert chat.call_count == 1
    assert not images.called
    assert draft.kind == "draft"
    assert [v.variant_id for v in draft.variants] == ["v1", "v2"]
    first = draft.variants[0]
    assert first.target_audience.startswith("Audience 1")
    assert first.image_prompt == "Scene 1: warm living room wall"
    assert (first.spec.width, first.spec.height, first.spec.aspect_ratio) == (1080, 1080, "1:1")
    assert draft.estimated_paid_calls == 2  # 2 images, no artwork so no SAM call


def test_draft_estimate_counts_sam_when_artwork_sent() -> None:
    from src.models.creative import CreativeBrief
    from src.services.ad_creative import to_editable_brief

    request = GenerateAdsRequest.model_validate(
        {
            "product": {"title": "Golden Temple", "image_url": "https://example.com/a.png"},
            "brief": _draft_brief().model_dump(),
            "placements": ["facebook_feed"],
            "variants_per_placement": 1,
        }
    )
    editable = to_editable_brief(CreativeBrief.model_validate(BRIEF_LLM), request)
    assert len(editable.variants) == 1
    assert editable.estimated_paid_calls == 2


@respx.mock
async def test_phase_two_renders_the_edited_brief_without_muse_spark(tmp_path: Path) -> None:
    chat = respx.post(f"{META_BASE_URL}/chat/completions")
    images = respx.post(f"{META_BASE_URL}/images/generations").mock(return_value=_image_response())

    edited = _draft_brief()
    edited.variants[0].include = False
    edited.variants[1].placement = "instagram_feed"
    edited.variants[1].headline = "Edited headline"
    edited.variants[1].image_prompt = "Edited: gurdwara courtyard at dusk"

    async with httpx.AsyncClient() as http_client:
        result = await _service(http_client, tmp_path).generate(
            GenerateAdsRequest(
                product=ProductInfo(title="Golden Temple"), brief=edited, use_comfyui=False
            )
        )

    assert not chat.called
    assert images.call_count == 1
    sent = json.loads(images.calls[0].request.content)
    assert sent["prompt"] == "Edited: gurdwara courtyard at dusk"
    assert sent["size"] == "1024x1280"
    assert result.kind == "creative_set"
    [creative] = result.creatives
    assert (creative.variant_id, creative.placement) == ("v2", "instagram_feed")
    assert creative.headline == "Edited headline"
    assert creative.target_audience == "Collectors of Punjabi folk art"


def test_request_validation_for_the_two_phases(competitor_brief: CompetitorBrief) -> None:
    product = ProductInfo(title="Golden Temple")
    with pytest.raises(ValidationError, match="competitor_brief is required"):
        GenerateAdsRequest(product=product)
    with pytest.raises(ValidationError, match="not both"):
        GenerateAdsRequest(product=product, draft=True, brief=_draft_brief())
    assert GenerateAdsRequest(product=product, brief=_draft_brief()).competitor_brief is None
    with pytest.raises(ValidationError):
        EditableCreativeVariant(
            variant_id="v1",
            placement="facebook_feed",
            headline="x" * 121,
            primary_text="t",
            image_prompt="p",
        )


class FakeCreativeService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def draft(self, request: GenerateAdsRequest) -> EditableCreativeBrief:
        self.calls.append("draft")
        return _draft_brief()

    async def generate(self, request: GenerateAdsRequest) -> CreativeSet:
        self.calls.append("generate")
        return CreativeSet(product_title=request.product.title, creatives=[])


@pytest.fixture
def fake_service() -> Any:
    fake = FakeCreativeService()
    app.dependency_overrides[get_ad_creative_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_generate_ads_route_two_phase(fake_service: FakeCreativeService, brief_json: dict) -> None:
    client = TestClient(app)
    product = {"title": "Golden Temple"}

    draft = client.post(
        "/api/v1/generate-ads",
        json={"product": product, "competitor_brief": brief_json, "draft": True},
    )
    assert draft.status_code == 200
    assert draft.json()["kind"] == "draft"
    assert draft.json()["variants"][1]["target_audience"] == "Collectors of Punjabi folk art"

    edited = draft.json()
    edited["variants"][0]["headline"] = "Edited by the seller"
    rendered = client.post("/api/v1/generate-ads", json={"product": product, "brief": edited})
    assert rendered.status_code == 200
    assert rendered.json()["kind"] == "creative_set"
    assert fake_service.calls == ["draft", "generate"]

    assert client.post("/api/v1/generate-ads", json={"product": product}).status_code == 422
