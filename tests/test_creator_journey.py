"""Regression test suite for the guided creator journey (/create).

Validates the full creator workflow: product/workspace selection,
dynamic export generation with user edits, saved vs live provenance,
error recovery, double-click protection, and inline media delivery.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_creator_journey_smoke_node_runner(tmp_path: Path, client: TestClient) -> None:
    """Execute tests/creator_journey_smoke.cjs via Node.js VM harness with live presets."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute creator_journey_smoke.cjs")

    root = Path(__file__).resolve().parents[1]
    presets_resp = client.get("/api/v1/demo-presets")
    assert presets_resp.status_code == 200

    presets_file = tmp_path / "presets.json"
    presets_file.write_text(json.dumps(presets_resp.json()), encoding="utf-8")

    result = subprocess.run(
        [
            node,
            str(root / "tests/creator_journey_smoke.cjs"),
            str(root / "src/api/static/creator.js"),
            str(presets_file),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ALL CREATOR JOURNEY SMOKE TESTS PASSED" in result.stdout


def test_creator_html_and_static_assets_contract(client: TestClient) -> None:
    """Verify /create route and that all referenced assets are served with proper headers."""
    response = client.get("/create")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    html = response.text
    assert 'href="/static/creator.css"' in html
    assert 'src="/static/creator.js"' in html
    assert 'data-panel="0"' in html
    assert 'data-panel="3"' in html

    css_resp = client.get("/static/creator.css")
    assert css_resp.status_code == 200
    assert len(css_resp.content) > 100

    js_resp = client.get("/static/creator.js")
    assert js_resp.status_code == 200
    assert "window.museCreatorSnapshot" in js_resp.text


def test_readiness_contract_does_not_leak_secrets(monkeypatch, client: TestClient) -> None:
    """Ensure readiness endpoint reports boolean flags and never leaks secret strings."""
    secret_key = "super-secret-provider-key-12345"
    unlock_key = "my-private-unlock-key-9999"
    monkeypatch.setenv("META_MODEL_API_KEY", secret_key)
    monkeypatch.setenv("DEMO_KEY", unlock_key)
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()

    resp = client.get("/api/v1/readiness")
    assert resp.status_code == 200
    data = resp.json()

    assert data["default_mode"] == "saved"
    assert data["provider_key_configured"] is True
    assert data["live_unlock_configured"] is True
    assert data["provider_verified"] is False

    assert secret_key not in resp.text
    assert unlock_key not in resp.text


def test_workspaces_contain_required_showcase_metadata(client: TestClient) -> None:
    """Verify presets endpoint provides distinct showcases for Sarabjit Singh and Saffron & Clay."""
    resp = client.get("/api/v1/demo-presets")
    assert resp.status_code == 200
    workspaces = resp.json().get("workspaces", {})

    assert "sarabjit_singh" in workspaces
    assert "etsy_ceramics" in workspaces

    art_ws = workspaces["sarabjit_singh"]
    assert art_ws["name"] == "Art of Sarabjit Singh"
    assert len(art_ws["artworks_showcase"]) > 0
    assert "Ek Onkar" in art_ws["artworks_showcase"][0]["title"]

    ceramics_ws = workspaces["etsy_ceramics"]
    assert ceramics_ws["name"] == "Saffron & Clay Studio"
    assert len(ceramics_ws["artworks_showcase"]) > 0
    assert "Chai" in ceramics_ws["artworks_showcase"][0]["title"]


def test_demo_generate_ads_preserves_contract(monkeypatch, client: TestClient) -> None:
    """Verify demo ad generation returns cached creative without paid calls."""
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    payload = {
        "product": {
            "title": "Ek Onkar · 12×12-inch print",
            "description": "Original artwork by Sarabjit Singh",
            "price": "$75",
        },
        "draft": False,
        "placements": ["instagram_feed"],
        "variants_per_placement": 1,
        "brief": {
            "product_title": "Ek Onkar · 12×12-inch print",
            "positioning_hook": "Museum-quality fine art print",
            "preserve_product_note": "Preserve brushwork",
            "estimated_paid_calls": 0,
            "variants": [
                {
                    "variant_id": "v1",
                    "include": True,
                    "placement": "instagram_feed",
                    "headline": "Sacred Art for Contemplative Spaces",
                    "primary_text": "Bring tranquility home.",
                    "image_prompt": "Minimalist collector interior",
                    "target_audience": "Art collectors",
                    "angle_rationale": "Cultural heritage",
                }
            ],
        },
    }

    resp = client.post("/api/v1/generate-ads", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "creatives" in data
    assert len(data["creatives"]) > 0
    creative = data["creatives"][0]
    assert "demo-cache" in str(creative.get("produced_by", ""))
