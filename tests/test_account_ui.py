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


def test_signup_auto_confirms_and_signs_in_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/v1/account/signup creates a confirmed user and returns an active session."""
    user_a = AccountSession(
        user_id="00000000-0000-4000-8000-000000000001",
        email="new@example.test",
        email_verified=True,
        access_token="access-token-new",
        session_id=None,
    )
    auth_calls: list[tuple[str, str, bool]] = []

    class FakeSupabase:
        async def auth(
            self,
            path: str,
            method: str = "GET",
            body: dict[str, Any] | None = None,
            access_token: str | None = None,
            secret: bool = False,
        ) -> dict[str, Any]:
            auth_calls.append((path, method, secret))
            if path == "admin/users":
                assert body == {
                    "email": "new@example.test",
                    "password": "very-secure-password-123",
                    "email_confirm": True,
                }
                return {"id": user_a.user_id, "email": user_a.email}
            if path == "token?grant_type=password":
                return {
                    "access_token": "access-token-new",
                    "refresh_token": "refresh-token-new",
                    "expires_in": 3600,
                }
            raise AssertionError(f"Unexpected auth call: {path}")

        async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
            assert name == "muse_usage_status"
            return {
                "allowed": True,
                "plan": "trial",
                "used": 0,
                "limit": 3,
                "remaining": 3,
                "resets_at": None,
                "live_available": True,
            }

    async def fake_verify(token: str) -> AccountSession:
        assert token == "access-token-new"
        return user_a

    monkeypatch.setattr("src.api.accounts.get_supabase_client", lambda: FakeSupabase())
    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: FakeSupabase())
    monkeypatch.setattr(accounts_service, "configured", lambda: True)
    monkeypatch.setattr("src.api.accounts.verify_token", fake_verify)
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/account/signup",
            headers={"Origin": "http://localhost:8000"},
            json={"email": "New@Example.test", "password": "very-secure-password-123"},
        )
    finally:
        get_settings.cache_clear()

    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "new@example.test"
    assert data["user"]["email_verified"] is True
    assert data["usage"]["remaining"] == 3
    assert "muse_access" in res.cookies
    assert auth_calls == [
        ("admin/users", "POST", True),
        ("token?grant_type=password", "POST", False),
    ]


def test_google_oauth_start_and_callback_mint_verified_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/v1/account/oauth and callback routes support Google OAuth."""
    user_g = AccountSession(
        user_id="00000000-0000-4000-8000-000000000009",
        email="founder@example.test",
        email_verified=True,
        access_token="google-supabase-access",
        session_id=None,
    )

    class FakeSupabase:
        async def auth(
            self,
            path: str,
            method: str = "GET",
            body: dict[str, Any] | None = None,
            access_token: str | None = None,
            secret: bool = False,
        ) -> dict[str, Any]:
            if path == "settings":
                return {"external": {"google": True}}
            if path == "admin/generate_link":
                assert secret is True
                assert body == {"type": "magiclink", "email": "founder@example.test"}
                return {"hashed_token": "hashed-magic-123"}
            if path == "verify":
                assert body == {"type": "magiclink", "token_hash": "hashed-magic-123"}
                return {
                    "access_token": "google-supabase-access",
                    "refresh_token": "google-supabase-refresh",
                    "expires_in": 3600,
                }
            raise AssertionError(f"Unexpected auth path: {path}")

    async def fake_verify(token: str) -> AccountSession:
        assert token == "google-supabase-access"
        return user_g

    monkeypatch.setattr(accounts_service, "get_supabase_client", lambda: FakeSupabase())
    monkeypatch.setattr(accounts_service, "configured", lambda: True)
    monkeypatch.setattr(accounts_service, "verify_token", fake_verify)
    monkeypatch.setenv("ACCOUNTS_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "secret-test-key")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app)
        # 1. Supabase external.google provider path
        supabase_oauth = client.post(
            "/api/v1/account/oauth",
            headers={"Origin": "http://localhost:8000"},
            json={"provider": "google", "next": "/create"},
        )
        assert supabase_oauth.status_code == 200
        assert supabase_oauth.json()["url"].startswith(
            "https://example.supabase.co/auth/v1/authorize?provider=google"
        )

        # 2. Direct GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET path + callback
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id.apps.googleusercontent.com")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
        get_settings.cache_clear()

        direct_oauth = client.post(
            "/api/v1/account/oauth",
            headers={"Origin": "http://localhost:8000"},
            json={"provider": "google", "next": "/today"},
        )
        assert direct_oauth.status_code == 200
        assert direct_oauth.json()["url"].startswith(
            "https://accounts.google.com/o/oauth2/v2/auth?"
        )
        state_cookie = direct_oauth.cookies.get("muse_oauth_state")
        assert state_cookie

        class FakeGoogleHttp:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FakeGoogleHttp:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            async def post(self, url: str, **kwargs: Any) -> Any:
                assert url == "https://oauth2.googleapis.com/token"
                return type(
                    "Resp",
                    (),
                    {"is_error": False, "json": lambda self: {"access_token": "goog-tok"}},
                )()

            async def get(self, url: str, **kwargs: Any) -> Any:
                assert url == "https://openidconnect.googleapis.com/v1/userinfo"
                return type(
                    "Resp",
                    (),
                    {
                        "is_error": False,
                        "json": lambda self: {
                            "email": "Founder@Example.test",
                            "email_verified": True,
                        },
                    },
                )()

        monkeypatch.setattr(accounts_service.httpx, "AsyncClient", FakeGoogleHttp)
        client.cookies.set("muse_oauth_state", state_cookie)
        cb = client.get(
            f"/api/v1/account/oauth/google/callback?code=auth-code-123&state={state_cookie}",
            follow_redirects=False,
        )
        assert cb.status_code == 302
        assert cb.headers["location"] == "/today?oauth=google"
        assert "muse_access=" in cb.headers.get("set-cookie", "")
    finally:
        get_settings.cache_clear()
