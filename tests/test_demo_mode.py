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


def test_demo_mode_guarded_seller_audit_screenshot_and_csv_routes(
    demo_client: TestClient, brief_json: dict[str, Any]
) -> None:
    service = CountingBidService()
    app.dependency_overrides[get_bid_advisor_service] = lambda: service

    presets = demo_client.get("/api/v1/demo-presets").json()
    profile = presets["workspaces"]["sarabjit_singh"]["profile"]

    # 1. Seller audit falls back to deterministic diagnostics in demo mode (no LLM call)
    audit_resp = demo_client.post(
        "/api/v1/audit-seller",
        json={"profile": profile, "deterministic_only": False},
    )
    assert audit_resp.status_code == 200
    diag = audit_resp.json()
    assert diag["total_platforms"] == 7
    assert diag["total_artworks_indexed"] == 72
    assert "executive_summary" not in diag

    # 2. Screenshot vision audit is blocked with 403 in demo mode without live key
    screenshot_resp = demo_client.post(
        "/api/v1/audit-screenshot",
        json={
            "image_base64": (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
                "2mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        },
    )
    assert screenshot_resp.status_code == 403
    assert "Screenshot analysis has no saved demo result" in screenshot_resp.json()["detail"]

    # 3. CSV bid advice serves cached recommendation in demo mode after validating CSV
    valid_csv = (
        "day,campaign_name,ad_set_name,impressions,clicks,conversions,spend,conversion_value\n"
        "2026-10-21,Fall Prints,Retargeting - Site Visitors,7700,231,10,70.00,620.00\n"
    )
    csv_cached = demo_client.post(
        "/api/v1/bid-advice/csv",
        json={"csv_text": valid_csv, "competitor_brief": brief_json},
    )
    assert csv_cached.status_code == 200
    assert csv_cached.json()["model"] == "muse-spark-1.3"
    assert service.calls == 0

    # 4. CSV deterministic_only returns computed PerformanceMetrics for the uploaded rows
    csv_det = demo_client.post(
        "/api/v1/bid-advice/csv",
        json={"csv_text": valid_csv, "deterministic_only": True},
    )
    assert csv_det.status_code == 200
    assert csv_det.json()["account_totals"]["spend"] == 70.0


@pytest.mark.parametrize(
    "bad_csv",
    [
        "wrong_col_a,wrong_col_b\n1,2\n",
        "day,campaign_name,ad_set_name,impressions,spend\nnot-a-date,Camp,Set,100,10.0\n",
        "day,campaign_name,ad_set_name,impressions,spend\n2026-10-21,Camp,Set,not-a-number,10.0\n",
    ],
)
def test_csv_validation_edge_cases_return_422_in_demo_mode(
    demo_client: TestClient, brief_json: dict[str, Any], bad_csv: str
) -> None:
    resp = demo_client.post(
        "/api/v1/bid-advice/csv",
        json={"csv_text": bad_csv, "competitor_brief": brief_json},
    )
    assert resp.status_code == 422
    assert "Invalid campaign CSV" in resp.json()["detail"]


def test_public_portal_and_all_sample_assets_resolve(demo_client: TestClient) -> None:
    from src.services.demo import DEMO_IMAGES

    assert demo_client.get("/").status_code == 200
    assert demo_client.get("/portal").status_code == 200

    presets = demo_client.get("/api/v1/demo-presets").json()
    asset_urls: set[str] = {f"/samples/{name}" for name in DEMO_IMAGES}
    for ws in presets["workspaces"].values():
        for item in ws.get("artworks_showcase", []):
            for key in ("original_image", "secondary_image", "staged_image", "mask_image"):
                val = item.get(key)
                if isinstance(val, str) and val.startswith("/samples/"):
                    asset_urls.add(val)

    assert len(asset_urls) >= 9
    for url in sorted(asset_urls):
        resp = demo_client.get(url)
        assert resp.status_code == 200, f"Missing sample asset: {url}"
        assert len(resp.content) > 1000
