"""Tests for Step 4b: Non-Sample Artist Workspace Isolation.

Nav's correction (Nov 10):
The end customer is any independent or small artist. Sikh art, SikhiArt.com and
the four watchlist competitors belong strictly to the sample shop (Art of Sarabjit Singh).
Nothing about that niche may be assumed for a real account.

This test proves:
A fixture account for a different kind of artist (Elena Vance Watercolor Studio,
landscape and botanical watercolor prints) completes onboarding, loads its workspace,
and sees ZERO sample-shop terms anywhere in its workspace data, suggestions, or directives.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.accounts import AccountSession

FORBIDDEN_SAMPLE_TERMS = [
    "Sikh",
    "Sarabjit",
    "Gurpurab",
    "Vaisakhi",
    "Ek Onkar",
    "SikhiArt",
    "Triton Museum",
    "Kala Sangam",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_non_sample_artist_onboarding_and_zero_sample_terms(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A landscape watercolor artist completes onboarding and sees ZERO sample-shop terms."""
    # 1. Real artist account session
    user = AccountSession(
        user_id="99999999-9999-4000-8000-999999999999",
        email="elena@wildmeadowstudio.com",
        email_verified=True,
        access_token="token-elena",
        session_id=None,
    )
    workspace_store: dict[str, Any] = {"document": {}, "version": 1}

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {
            "document": workspace_store["document"],
            "version": workspace_store["version"],
            "owner_id": user.user_id,
        }

    async def fake_save(
        _account: AccountSession,
        doc: dict[str, Any],
        expected_version: Any = None,
        expected_owner: Any = None,
    ) -> dict[str, Any]:
        workspace_store["document"] = doc
        workspace_store["version"] += 1
        return {"document": doc, "version": workspace_store["version"], "owner_id": user.user_id}

    async def fake_snapshot(_account: AccountSession) -> dict[str, Any]:
        return {
            "configured": True,
            "user": {"id": user.user_id, "email": user.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3, "resets_at": None},
            "live_available": True,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)

    monkeypatch.setattr("src.api.directives.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.directives.load_workspace", fake_load)

    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)

    monkeypatch.setattr("src.api.outcomes.resolve_account", fake_resolve)

    # 2. Complete onboarding with real watercolor artist shop data
    build_payload = {
        "business_name": "Elena Vance Watercolor Studio",
        "shop_urls": [
            "https://elenavanceart.com",
            "https://elenavanceart.etsy.com",
        ],
        "socials": [{"platform": "instagram", "handle": "@elenavanceart"}],
        "competitors": [
            {
                "name": "Wild Meadow Studio",
                "url": "https://www.wildmeadowstudio.com",
                "reason": "Botanical and landscape watercolor prints",
            }
        ],
        "preferences": {
            "medium": "Watercolor & Gouache",
            "price_range": "$25–$180",
        },
    }

    resp = client.post(
        "/api/v1/onboarding/build",
        json=build_payload,
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
    )
    assert resp.status_code == 200, f"Onboarding failed: {resp.text}"
    onboarding_data = resp.json()
    assert onboarding_data["success"] is True

    # 3. Retrieve account workspace and verify zero sample terms
    ws_doc = workspace_store["document"]
    ws_text = str(ws_doc)

    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in ws_text.lower(), (
            f"Sample term '{term}' leaked into watercolor workspace document!"
        )

    # 4. Verify directives suggestions adapt to this artist and competitor
    sug_resp = client.get("/api/v1/directives/suggestions")
    assert sug_resp.status_code == 200
    suggestions = sug_resp.json()
    assert len(suggestions) >= 4

    pricing_sug = suggestions[0]["text"]
    assert "Wild Meadow Studio" in pricing_sug or "competitor entry prices" in pricing_sug
    assert "SikhiArt" not in pricing_sug

    all_sug_text = " ".join(s["text"] for s in suggestions)
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in all_sug_text.lower(), (
            f"Sample term '{term}' leaked into watercolor suggestions: {all_sug_text}"
        )

    # 5. Verify outcomes are scoped to this account without sample leak
    outcomes_resp = client.get("/api/v1/outcomes")
    assert outcomes_resp.status_code == 200
    outcomes_data = outcomes_resp.json()
    assert len(outcomes_data["outcomes"]) == 0
    assert outcomes_data["summary"]["moves_count"] == 0
    assert outcomes_data["summary"]["net_roi_usd"] is None

    outcomes_text = str(outcomes_data)
    for term in FORBIDDEN_SAMPLE_TERMS:
        assert term.lower() not in outcomes_text.lower(), (
            f"Sample term '{term}' leaked into watercolor outcomes!"
        )
