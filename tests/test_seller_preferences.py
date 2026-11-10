"""Tests for Track D: SellerPreferences, signals synchronization, and deterministic idea ranking."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.intel import ActionableInsight
from src.models.seller import (
    AccessPreferences,
    DismissSignal,
    SellerPreferences,
    TastePreferences,
)
from src.services.accounts import AccountSession
from src.services.preference_ranker import rank_ideas_deterministically

USER_ID = "77777777-7777-4000-8000-777777777777"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_ideas() -> list[ActionableInsight]:
    """5 representative candidate ideas covering different channels, difficulty, and pricing."""
    return [
        ActionableInsight(
            title="Reallocate Meta ad budget to retargeting",
            action="Shift $15/day from fatigued prospecting ad sets to 9.3x ROAS retargeting.",
            why="7-day ROAS dropped below 1.5x on cold audiences while retargeting converts.",
            priority="high",
        ),
        ActionableInsight(
            title="Add a cheap starter print at $14 to $22",
            action="List one small print from your Guru Nanak series at $14 on your site.",
            why="Competitor entry pricing is $59.99, leaving a gap for gift shoppers.",
            priority="high",
        ),
        ActionableInsight(
            title="Make a Sikh Women shop group",
            action="Group Mai Bhago, Mata Gujri and empowerment works in one collection.",
            why="Competitor has warrior series but lacks curated women heritage collections.",
            priority="medium",
        ),
        ActionableInsight(
            title="Launch framed holiday gift sets",
            action="Offer ready-to-hang framed bundles for seasonal decor.",
            why="Q4 gift queries peak for framed archival artwork.",
            priority="medium",
        ),
        ActionableInsight(
            title="Etsy limited edition series promo",
            action="List signed limited prints on Etsy with custom certificates.",
            why="Etsy search volume for signed heritage prints is up 22%.",
            priority="low",
        ),
    ]


# ---------------------------------------------------------------------------
# 1. SellerPreferences model checks
# ---------------------------------------------------------------------------


def test_seller_preferences_defaults_and_validation() -> None:
    pref = SellerPreferences()
    assert pref.experience == "some"
    assert pref.access.can_change_prices is True
    assert pref.version == 1

    custom = SellerPreferences(
        experience="new",
        access=AccessPreferences(channels=["instagram", "shopify"], can_change_prices=False),
        taste=TastePreferences(tone="reverent", subjects_to_avoid=["politics"]),
        research_focus="Focus on museum-grade fine art prints",
    )
    assert custom.experience == "new"
    assert custom.access.can_change_prices is False
    assert "instagram" in custom.access.channels
    assert "politics" in custom.taste.subjects_to_avoid


# ---------------------------------------------------------------------------
# 2. Deterministic ranking behavior
# ---------------------------------------------------------------------------


def test_new_seller_never_sees_ad_budget_first(sample_ideas: list[ActionableInsight]) -> None:
    """A new seller never sees complex ad budget reallocation as top recommendation."""
    pref = SellerPreferences(experience="new")
    ranked = rank_ideas_deterministically(sample_ideas, preferences=pref)

    # Top recommendation must NOT be the advanced Meta ad budget move
    assert "ad budget" not in ranked[0].title.lower()
    # Simpler moves (e.g. starter print or shop group) rank higher
    top_titles = [r.title for r in ranked[:2]]
    assert any("starter print" in t.lower() or "shop group" in t.lower() for t in top_titles)


def test_seller_without_price_control_never_sees_pricing_moves_as_do_it_now(
    sample_ideas: list[ActionableInsight],
) -> None:
    """A seller who cannot change prices never sees pricing moves as do-it-now."""
    pref = SellerPreferences(
        access=AccessPreferences(can_change_prices=False),
    )
    ranked = rank_ideas_deterministically(sample_ideas, preferences=pref)

    # The starter print pricing move is demoted from top rank
    assert "starter print" not in ranked[0].title.lower()
    assert "cheap" not in ranked[0].title.lower()


def test_two_too_advanced_dismissals_lowers_difficulty(
    sample_ideas: list[ActionableInsight],
) -> None:
    """2+ 'too_advanced' dismissals deprioritizes high-difficulty recommendations."""
    signals = [
        DismissSignal(id="a1", title="Scale Meta lookalike audience", reason="too_advanced"),
        DismissSignal(id="a2", title="Set up server-side Conversions API", reason="too_advanced"),
    ]
    ranked = rank_ideas_deterministically(sample_ideas, dismiss_signals=signals)

    # The advanced ad budget reallocation is pushed down
    assert "ad budget" not in ranked[0].title.lower()
    # Simpler creative or collection actions rank first
    assert any("shop group" in r.title.lower() or "starter" in r.title.lower() for r in ranked[:2])


def test_no_access_signal_hides_channel(sample_ideas: list[ActionableInsight]) -> None:
    """Dismissing with 'no_access' on a channel hides that channel from recommendations."""
    signals = [
        DismissSignal(id="a5", title="Etsy print set promo", channel="etsy", reason="no_access"),
    ]
    ranked = rank_ideas_deterministically(sample_ideas, dismiss_signals=signals)

    # All Etsy recommendations are filtered out
    assert not any("etsy" in r.title.lower() or "etsy" in r.action.lower() for r in ranked)


def test_already_tried_signal_filters_or_demotes_idea(
    sample_ideas: list[ActionableInsight],
) -> None:
    """Dismissing with 'already_tried' filters out that specific idea."""
    signals = [
        DismissSignal(
            id="a2",
            title="Add a cheap starter print at $14 to $22",
            reason="already_tried",
        ),
    ]
    ranked = rank_ideas_deterministically(sample_ideas, dismiss_signals=signals)

    # The starter print move is removed
    assert not any("starter print" in r.title.lower() for r in ranked)


# ---------------------------------------------------------------------------
# 3. Preferences & Signals API endpoints
# ---------------------------------------------------------------------------


def test_get_and_put_preferences_endpoints(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Verified accounts can GET and PUT their SellerPreferences."""
    user = AccountSession(
        user_id=USER_ID,
        email="seller@example.test",
        email_verified=True,
        access_token="tok",
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

    monkeypatch.setattr("src.api.preferences.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.preferences.load_workspace", fake_load)
    monkeypatch.setattr("src.api.preferences.save_workspace", fake_save)

    headers = {"X-Muse-Owner": user.user_id}

    # 1. GET default preferences
    get_resp = client.get("/api/v1/preferences", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["experience"] == "some"

    # 2. PUT updated preferences
    update_payload = {
        "experience": "new",
        "access": {"channels": ["instagram", "pixels"], "can_change_prices": False},
        "taste": {"tone": "playful", "subjects_to_avoid": ["military"]},
        "research_focus": "Handmade ceramic pottery gifts",
    }
    put_resp = client.put("/api/v1/preferences", json=update_payload, headers=headers)
    assert put_resp.status_code == 200
    assert put_resp.json()["experience"] == "new"
    assert put_resp.json()["access"]["can_change_prices"] is False
    assert workspace_store["document"]["preferences"]["experience"] == "new"


def test_sync_signals_endpoint(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Client can sync muse.actions and muse.dismiss_signals to account workspace."""
    user = AccountSession(
        user_id=USER_ID,
        email="seller@example.test",
        email_verified=True,
        access_token="tok",
        session_id=None,
    )
    workspace_store: dict[str, Any] = {"document": {}, "version": 2}

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

    monkeypatch.setattr("src.api.preferences.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.preferences.load_workspace", fake_load)
    monkeypatch.setattr("src.api.preferences.save_workspace", fake_save)

    headers = {"X-Muse-Owner": user.user_id}

    payload = {
        "actions": {
            "a1": {"status": "accepted", "title": "Add a cheap starter print"},
            "a2": {"status": "done", "title": "Make a Sikh Women shop group"},
        },
        "dismiss_signals": [
            {
                "id": "a3",
                "title": "Etsy print set promo",
                "reason": "no_access",
                "at": "2026-11-10T12:00:00Z",
            },
        ],
    }

    resp = client.post("/api/v1/preferences/signals", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["actions_count"] == 2
    assert data["signals_count"] == 1
    assert "a1" in workspace_store["document"]["actions"]
    assert workspace_store["document"]["dismiss_signals"][0]["reason"] == "no_access"


def test_rank_endpoint(client: TestClient, sample_ideas: list[ActionableInsight]) -> None:
    """POST /preferences/rank returns deterministically filtered and ordered ideas."""
    payload = {
        "ideas": [i.model_dump(mode="json") for i in sample_ideas],
        "preferences": {
            "experience": "new",
            "access": {"can_change_prices": True},
        },
        "dismiss_signals": [
            {"id": "a5", "title": "Etsy promo", "channel": "etsy", "reason": "no_access"},
        ],
    }
    resp = client.post("/api/v1/preferences/rank", json=payload)
    assert resp.status_code == 200
    ranked = resp.json()

    # Ad budget is not top for new seller
    assert "ad budget" not in ranked[0]["title"].lower()
    # Etsy is filtered out
    assert not any("etsy" in r["title"].lower() for r in ranked)
