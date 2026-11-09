"""Execute the account UI contract (signup/signin/quota/workspace) via Node.js."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.services import accounts as accounts_service
from src.services.accounts import AccountSession


def test_account_ui_contract_node_runner() -> None:
    """Execute tests/account_ui_contract.cjs via Node.js VM harness."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute account_ui_contract.cjs")

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/account_ui_contract.cjs")],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ACCOUNT UI CONTRACT PASSED" in result.stdout


def test_workspace_get_binds_owner_and_rejects_cross_tab_cookie_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/v1/account/workspace returns owner_id and rejects mismatched X-Muse-Owner."""
    user_b = AccountSession(
        user_id="00000000-0000-4000-8000-000000000002",
        email="b@example.test",
        email_verified=True,
        access_token="token-b",
        session_id=None,
    )
    workspace_calls: list[str] = []

    class FakeSupabase:
        async def workspace(self, user_id: str) -> list[dict[str, Any]]:
            workspace_calls.append(user_id)
            return [{"document": {"documents": {"daily": {"hook": "B secret"}}}, "version": 4}]

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user_b

    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: FakeSupabase())

    client = TestClient(app)
    mismatch = client.get(
        "/api/v1/account/workspace",
        headers={"X-Muse-Owner": "00000000-0000-4000-8000-000000000001"},
    )
    assert mismatch.status_code == 409
    assert "account changed" in mismatch.json()["detail"].lower()
    assert workspace_calls == []

    matched = client.get(
        "/api/v1/account/workspace",
        headers={"X-Muse-Owner": user_b.user_id},
    )
    assert matched.status_code == 200
    payload = matched.json()
    assert payload["owner_id"] == user_b.user_id
    assert payload["version"] == 4
    assert workspace_calls == [user_b.user_id]


def test_workspace_put_requires_and_enforces_expected_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /api/v1/account/workspace blocks unbound or cross-tab owner saves before RPC."""
    user_b = AccountSession(
        user_id="00000000-0000-4000-8000-000000000002",
        email="b@example.test",
        email_verified=True,
        access_token="token-b",
        session_id=None,
    )
    rpc_calls: list[dict[str, Any]] = []

    class FakeSupabase:
        async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
            assert name == "muse_save_workspace"
            rpc_calls.append(params)
            return {"allowed": True, "version": 5}

    async def fake_resolve(*_args: Any, **_kwargs: Any) -> AccountSession:
        return user_b

    monkeypatch.setattr("src.api.accounts.resolve_account", fake_resolve)
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: FakeSupabase())

    client = TestClient(app)
    headers = {"Origin": "http://localhost:8000"}

    # Missing both expected_owner and X-Muse-Owner is rejected with 409.
    unbound = client.put(
        "/api/v1/account/workspace",
        headers=headers,
        json={"document": {"documents": {}}, "expected_version": 4},
    )
    assert unbound.status_code == 409
    assert rpc_calls == []

    # Cross-tab cookie switch: Tab 1 expects User A, but cookie resolved to User B.
    cross_tab_body = client.put(
        "/api/v1/account/workspace",
        headers=headers,
        json={
            "document": {"documents": {"creator": {"caption": "User A draft"}}},
            "expected_version": 4,
            "expected_owner": "00000000-0000-4000-8000-000000000001",
        },
    )
    assert cross_tab_body.status_code == 409
    assert "account changed" in cross_tab_body.json()["detail"].lower()
    assert rpc_calls == []

    cross_tab_header = client.put(
        "/api/v1/account/workspace",
        headers={**headers, "X-Muse-Owner": "00000000-0000-4000-8000-000000000001"},
        json={
            "document": {"documents": {"creator": {"caption": "User A draft"}}},
            "expected_version": 4,
            "expected_owner": user_b.user_id,
        },
    )
    assert cross_tab_header.status_code == 409
    assert rpc_calls == []

    # Matching owner succeeds and returns owner_id.
    valid = client.put(
        "/api/v1/account/workspace",
        headers={**headers, "X-Muse-Owner": user_b.user_id},
        json={
            "document": {"documents": {"creator": {"caption": "User B draft"}}},
            "expected_version": 4,
            "expected_owner": user_b.user_id,
        },
    )
    assert valid.status_code == 200
    saved = valid.json()
    assert saved["owner_id"] == user_b.user_id
    assert saved["version"] == 5
    assert len(rpc_calls) == 1
    assert rpc_calls[0]["p_user_id"] == user_b.user_id
