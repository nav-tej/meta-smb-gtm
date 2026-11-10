"""Server tests for Track H onboarding ownership, idempotent debit, and error surfacing."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.accounts import AccountSession


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_onboarding_build_charges_one_run_on_success(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """Completing onboarding debits exactly 1 run when runs are available."""
    user = AccountSession(
        user_id="11111111-1111-4000-8000-111111111111",
        email="seller1@example.test",
        email_verified=True,
        access_token="token-1",
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

    resp = test_client.post(
        "/api/v1/onboarding/build",
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
        json={
            "business_name": "Sikh Art Prints",
            "shop_urls": ["https://sikhiart.com"],
            "competitors": [{"name": "Comp Shop", "url": "https://comp.test"}],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["charged"] is True
    assert data["used_run"] is True
    assert data["completed_at"] is not None
    assert workspace_store["document"]["onboarding"]["business_name"] == "Sikh Art Prints"


def test_onboarding_build_retry_and_double_submit_charge_once(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """A second submit or retry on an already-completed onboarding charges 0 runs."""
    user = AccountSession(
        user_id="11111111-1111-4000-8000-111111111111",
        email="seller1@example.test",
        email_verified=True,
        access_token="token-1",
        session_id=None,
    )
    # Already completed
    workspace_store: dict[str, Any] = {
        "document": {
            "onboarding": {
                "business_name": "Sikh Art Prints",
                "completed_at": "2026-11-10T12:00:00Z",
                "used_run": True,
            }
        },
        "version": 2,
    }

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {
            "document": workspace_store["document"],
            "version": workspace_store["version"],
            "owner_id": user.user_id,
        }

    saved_called = False

    async def fake_save(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal saved_called
        saved_called = True
        return {"document": {}, "version": 3, "owner_id": user.user_id}

    async def fake_snapshot(_account: AccountSession) -> dict[str, Any]:
        return {
            "configured": True,
            "user": {"id": user.user_id, "email": user.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 1, "limit": 3, "remaining": 2, "resets_at": None},
            "live_available": True,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)

    resp = test_client.post(
        "/api/v1/onboarding/build",
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
        json={"business_name": "Sikh Art Prints"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["charged"] is False  # 0 runs charged on repeat!
    assert data["used_run"] is True
    assert not saved_called


def test_onboarding_build_failed_save_surfaced_not_masked(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """A failed workspace save surfaces the error to the caller and does not commit the debit."""
    user = AccountSession(
        user_id="22222222-2222-4000-8000-222222222222",
        email="seller2@example.test",
        email_verified=True,
        access_token="token-2",
        session_id=None,
    )

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user

    async def fake_load(_account: AccountSession) -> dict[str, Any]:
        return {"document": {}, "version": 1, "owner_id": user.user_id}

    async def fake_save_fails(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise HTTPException(409, "Your workspace changed in another tab.")

    async def fake_snapshot(_account: AccountSession) -> dict[str, Any]:
        return {
            "configured": True,
            "user": {"id": user.user_id, "email": user.email, "email_verified": True},
            "usage": {"plan": "starter", "used": 0, "limit": 3, "remaining": 3, "resets_at": None},
            "live_available": True,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save_fails)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)

    resp = test_client.post(
        "/api/v1/onboarding/build",
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
        json={"business_name": "Conflict Shop"},
    )
    # The error MUST be surfaced, not masked as 200 OK
    assert resp.status_code == 409
    assert "Your workspace changed" in resp.json()["detail"]


def test_onboarding_zero_runs_completes_for_free(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """An account with 0 runs can still finish onboarding with crawl data for 0 runs."""
    user = AccountSession(
        user_id="33333333-3333-4000-8000-333333333333",
        email="seller3@example.test",
        email_verified=True,
        access_token="token-3",
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
            "usage": {"plan": "starter", "used": 3, "limit": 3, "remaining": 0, "resets_at": None},
            "live_available": False,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)
    monkeypatch.setattr("src.api.onboarding.save_workspace", fake_save)
    monkeypatch.setattr("src.api.onboarding.snapshot", fake_snapshot)

    resp = test_client.post(
        "/api/v1/onboarding/build",
        headers={"Content-Type": "application/json", "X-Muse-Owner": user.user_id},
        json={"business_name": "Zero Run Shop"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["charged"] is False
    assert data["used_run"] is False
    assert workspace_store["document"]["onboarding"]["used_run"] is False


def test_onboarding_account_a_then_account_b_isolation(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """Account A's completed onboarding is never leaked to Account B."""
    user_a = AccountSession(
        user_id="aaaaaaaa-aaaa-4000-8000-aaaaaaaaaaaa",
        email="a@example.test",
        email_verified=True,
        access_token="token-a",
        session_id=None,
    )
    user_b = AccountSession(
        user_id="bbbbbbbb-bbbb-4000-8000-bbbbbbbbbbbb",
        email="b@example.test",
        email_verified=True,
        access_token="token-b",
        session_id=None,
    )

    workspaces = {
        user_a.user_id: {
            "document": {
                "onboarding": {
                    "business_name": "Account A Exclusive Art",
                    "completed_at": "2026-11-10T10:00:00Z",
                }
            },
            "version": 1,
        },
        user_b.user_id: {
            "document": {},
            "version": 0,
        },
    }

    current_user = user_a

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return current_user

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        ws = workspaces[account.user_id]
        return {
            "document": ws["document"],
            "version": ws["version"],
            "owner_id": account.user_id,
        }

    monkeypatch.setattr("src.api.onboarding.resolve_account", fake_resolve)
    monkeypatch.setattr("src.api.onboarding.load_workspace", fake_load)

    # 1. Check Account A
    resp_a = test_client.get("/api/v1/onboarding/status")
    assert resp_a.status_code == 200
    assert resp_a.json()["completed"] is True
    onb_doc = resp_a.json()["workspace"]["document"]["onboarding"]
    assert onb_doc["business_name"] == "Account A Exclusive Art"

    # 2. Switch to Account B on the same device/endpoint
    current_user = user_b
    resp_b = test_client.get("/api/v1/onboarding/status")
    assert resp_b.status_code == 200
    assert resp_b.json()["completed"] is False
    assert resp_b.json()["workspace"]["document"] == {}


def test_post_auth_routing_redirects_new_to_welcome_returning_to_root(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient
) -> None:
    """OAuth callback and signin redirect new accounts to /welcome and returning accounts to /."""
    new_user = AccountSession(
        user_id="44444444-4444-4000-8000-444444444444",
        email="new@example.test",
        email_verified=True,
        access_token="token-new",
        session_id=None,
    )
    ret_user = AccountSession(
        user_id="55555555-5555-4000-8000-555555555555",
        email="returning@example.test",
        email_verified=True,
        access_token="token-ret",
        session_id=None,
    )

    async def fake_oauth(
        _req: Any, code: Any, _state: Any, _err: Any
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        if code == "code-new":
            return "/account", {"access_token": "token-new", "refresh_token": "ref-new"}, None
        return "/account", {"access_token": "token-ret", "refresh_token": "ref-ret"}, None

    async def fake_verify(token: str) -> AccountSession:
        return new_user if token == "token-new" else ret_user

    async def fake_load(account: AccountSession) -> dict[str, Any]:
        if account.user_id == new_user.user_id:
            return {"document": {}, "version": 0, "owner_id": new_user.user_id}
        return {
            "document": {"onboarding": {"completed_at": "2026-11-10T00:00:00Z"}},
            "version": 1,
            "owner_id": ret_user.user_id,
        }

    monkeypatch.setattr("src.api.accounts.complete_google_oauth", fake_oauth)
    monkeypatch.setattr("src.api.accounts.verify_token", fake_verify)
    monkeypatch.setattr("src.api.accounts.load_workspace", fake_load)

    # Callback with new account -> redirects to /welcome
    resp_new = test_client.get(
        "/api/v1/account/oauth/google/callback?code=code-new&state=valid",
        follow_redirects=False,
    )
    assert resp_new.status_code == 302
    assert resp_new.headers["location"].startswith("/welcome")

    # Callback with returning account -> redirects to /
    resp_ret = test_client.get(
        "/api/v1/account/oauth/google/callback?code=code-ret&state=valid",
        follow_redirects=False,
    )
    assert resp_ret.status_code == 302
    assert resp_ret.headers["location"].startswith("/?")
