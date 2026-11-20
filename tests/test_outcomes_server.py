"""Tests for Track F: Verified seller outcomes, move logging, and honest ROI calculation."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.outcome import Outcome
from src.services.accounts import AccountSession
from src.services.outcomes import summarize_outcomes

USER_ID = "99999999-9999-4000-8000-999999999999"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Honest ROI summary logic tests
# ---------------------------------------------------------------------------


def test_summarize_outcomes_honest_zero_moves() -> None:
    """Zero logged moves must yield net_roi_usd = None (no invented negative or zero ROI)."""
    summary = summarize_outcomes([])
    assert summary.moves_count == 0
    assert summary.total_revenue_usd == 0.0
    assert summary.net_roi_usd is None
    assert summary.has_logged_result is False
    assert summary.plan_cost_usd == 12.0


def test_summarize_outcomes_honest_with_moves() -> None:
    """When seller logs real moves, net ROI is strictly revenue minus plan cost."""
    outcomes = [
        Outcome(
            title="Featured Spring Floral Vase",
            revenue=50.0,
            minutes=25,
            orders=2,
            clicks=15,
            reach=120,
        ),
        Outcome(
            title="Holiday gift bundle promo",
            revenue=35.50,
            minutes=15,
            orders=1,
            clicks=8,
            reach=80,
        ),
    ]
    summary = summarize_outcomes(outcomes, plan_cost_usd=12.0)
    assert summary.moves_count == 2
    assert summary.total_revenue_usd == 85.50
    assert summary.total_minutes == 40
    assert summary.total_orders == 3
    assert summary.has_logged_result is True
    # 85.50 - 12.0 = 73.50
    assert summary.net_roi_usd == 73.50


def test_summarize_outcomes_honest_zero_revenue_move() -> None:
    """A move with 0 revenue logged yields negative net ROI (-$12.00)."""
    outcomes = [
        Outcome(title="Test post without direct revenue", revenue=0.0, minutes=10),
    ]
    summary = summarize_outcomes(outcomes, plan_cost_usd=12.0)
    assert summary.moves_count == 1
    assert summary.total_revenue_usd == 0.0
    assert summary.net_roi_usd == -12.0
    assert summary.has_logged_result is True


# ---------------------------------------------------------------------------
# 2. Server API endpoints tests
# ---------------------------------------------------------------------------


def test_unauthenticated_outcomes_list(client: TestClient) -> None:
    """Unauthenticated GET /outcomes returns 200 with empty list and honest None ROI."""
    resp = client.get("/api/v1/outcomes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcomes"] == []
    assert data["summary"]["moves_count"] == 0
    assert data["summary"]["net_roi_usd"] is None
    assert data["summary"]["has_logged_result"] is False


def test_unauthenticated_post_outcome_rejected(client: TestClient) -> None:
    """Unauthenticated POST /outcomes requires a verified account."""
    payload = {"title": "Test Move", "revenue": 10.0}
    resp = client.post("/api/v1/outcomes", json=payload)
    assert resp.status_code == 401


def test_authenticated_save_and_list_outcomes(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Authenticated account can log moves, persist to workspace, and read list + summary."""
    user = AccountSession(
        user_id=USER_ID,
        email="seller@artist.test",
        email_verified=True,
        access_token="tok-outcomes",
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

    monkeypatch.setattr("src.api.outcomes.resolve_account", fake_resolve)
    monkeypatch.setattr("src.services.outcomes.load_workspace", fake_load)
    monkeypatch.setattr("src.services.outcomes.save_workspace", fake_save)

    headers = {"X-Muse-Owner": user.user_id}

    # 1. Initial list should be empty
    get_resp = client.get("/api/v1/outcomes", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["outcomes"] == []
    assert get_resp.json()["summary"]["net_roi_usd"] is None

    # 2. Log first move
    move1 = {
        "title": "Featured Spring Floral Vase",
        "channel": "instagram",
        "minutes": 20,
        "reach": 150,
        "clicks": 12,
        "orders": 1,
        "revenue": 50.0,
        "notes": "Posted to IG stories with product link.",
    }
    post_resp1 = client.post("/api/v1/outcomes", json=move1, headers=headers)
    assert post_resp1.status_code == 200
    res1 = post_resp1.json()
    assert res1["outcome"]["title"] == "Featured Spring Floral Vase"
    assert res1["outcome"]["revenue"] == 50.0
    assert res1["summary"]["moves_count"] == 1
    assert res1["summary"]["total_revenue_usd"] == 50.0
    assert res1["summary"]["net_roi_usd"] == 38.0  # 50 - 12
    assert res1["summary"]["has_logged_result"] is True

    # 3. Log second move
    move2 = {
        "title": "Email newsletter special offer",
        "channel": "email",
        "minutes": 15,
        "reach": 300,
        "clicks": 40,
        "orders": 3,
        "revenue": 95.0,
    }
    post_resp2 = client.post("/api/v1/outcomes", json=move2, headers=headers)
    assert post_resp2.status_code == 200
    res2 = post_resp2.json()
    assert res2["summary"]["moves_count"] == 2
    assert res2["summary"]["total_revenue_usd"] == 145.0
    assert res2["summary"]["net_roi_usd"] == 133.0  # 145 - 12

    # 4. Verify list returns both
    list_resp = client.get("/api/v1/outcomes", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data["outcomes"]) == 2
    assert list_data["summary"]["moves_count"] == 2
    assert list_data["summary"]["net_roi_usd"] == 133.0

    # 5. Verify /summary endpoint returns the same summary
    sum_resp = client.get("/api/v1/outcomes/summary", headers=headers)
    assert sum_resp.status_code == 200
    assert sum_resp.json()["moves_count"] == 2
    assert sum_resp.json()["net_roi_usd"] == 133.0


def test_owner_mismatch_rejected(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """X-Muse-Owner header mismatch returns 409 Conflict."""
    user = AccountSession(
        user_id=USER_ID,
        email="seller@artist.test",
        email_verified=True,
        access_token="tok-outcomes",
        session_id=None,
    )

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    monkeypatch.setattr("src.api.outcomes.resolve_account", fake_resolve)

    # Wrong owner header
    headers = {"X-Muse-Owner": "other-user-id"}
    resp = client.post(
        "/api/v1/outcomes",
        json={"title": "Test", "revenue": 10.0},
        headers=headers,
    )
    assert resp.status_code == 409
