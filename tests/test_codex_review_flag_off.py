"""Priority 1 independent review test: flag-off production safety with META_APP_ID/SECRET set."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients.ad_networks.base import AdNetworkDisabledError
from src.clients.ad_networks.meta import MetaAdsReadClient, exchange_meta_oauth_code
from src.config import get_settings
from src.services.ad_connections import (
    AdConnectionError,
    build_meta_oauth_authorize_url,
    complete_meta_oauth_callback,
)
from src.services.ad_insights import fetch_meta_campaign_performance


@pytest.fixture
def vercel_flag_off_env(monkeypatch: pytest.MonkeyPatch):
    """Simulate exact Vercel Production/Preview env shape: Meta app creds set, flag off."""
    monkeypatch.setenv("META_APP_ID", "123456789012345")
    monkeypatch.setenv("META_APP_SECRET", "dummy-secret-for-offline-test")
    monkeypatch.delenv("AD_TOKEN_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("META_LOGIN_CONFIG_ID", raising=False)
    monkeypatch.delenv("AD_CONNECT_ENABLED", raising=False)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("META_MODEL_API_KEY", "")
    monkeypatch.setenv("DEMO_KEY", "")
    get_settings.cache_clear()
    try:
        yield get_settings()
    finally:
        get_settings.cache_clear()


def test_flag_off_readiness_and_all_ad_account_routes_return_404(
    vercel_flag_off_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With META_APP_ID/SECRET set and AD_CONNECT_ENABLED unset, every route is disabled (404)."""
    rpc_calls: list[str] = []

    async def fail_if_rpc_called(*args: Any, **kwargs: Any) -> Any:
        rpc_calls.append(str(args))
        raise AssertionError("Supabase RPC must never be called when AD_CONNECT_ENABLED=false")

    monkeypatch.setattr("src.services.ad_connections._rpc", fail_if_rpc_called)

    client = TestClient(app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200

    readiness = client.get("/api/v1/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ad_connect_enabled"] is False

    openapi_paths = client.get("/openapi.json").json().get("paths", {})
    assert not any("/ad-accounts/meta" in p for p in openapi_paths), list(openapi_paths)

    routes = [
        ("GET", "/api/v1/ad-accounts/meta/connect"),
        ("POST", "/api/v1/ad-accounts/meta/connect"),
        ("GET", "/api/v1/ad-accounts/meta/callback?code=abc&state=xyz"),
        ("GET", "/api/v1/ad-accounts/meta/accounts"),
        ("GET", "/api/v1/ad-accounts/meta/insights?account_id=act_123"),
        ("POST", "/api/v1/ad-accounts/meta/insights"),
        ("POST", "/api/v1/ad-accounts/meta/disconnect"),
        ("DELETE", "/api/v1/ad-accounts/meta/disconnect?account_id=act_123"),
    ]
    for method, path in routes:
        resp = client.request(
            method,
            path,
            json={"account_id": "act_123"} if method == "POST" else None,
        )
        assert resp.status_code == 404, (method, path, resp.status_code, resp.text)

    assert rpc_calls == []


async def test_flag_off_meta_client_and_oauth_services_block_before_network_or_db(
    vercel_flag_off_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MetaAdsReadClient, OAuth helpers, and insights slice refuse to run when flag is off."""

    async def fail_rpc(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("RPC must not be called while AD_CONNECT_ENABLED=false")

    monkeypatch.setattr("src.services.ad_connections._rpc", fail_rpc)

    read_client = MetaAdsReadClient(access_token="dummy-token", settings=vercel_flag_off_env)
    try:
        with pytest.raises(AdNetworkDisabledError):
            await read_client.list_ad_accounts()
        with pytest.raises(AdNetworkDisabledError):
            await read_client.fetch_campaign_insights(
                "act_123", start_date=date(2026, 11, 1), end_date=date(2026, 11, 7)
            )
        with pytest.raises(AdNetworkDisabledError):
            await fetch_meta_campaign_performance(
                "act_123",
                start_date=date(2026, 11, 1),
                end_date=date(2026, 11, 7),
                client=read_client,
            )
    finally:
        await read_client.aclose()

    with pytest.raises(AdNetworkDisabledError):
        await exchange_meta_oauth_code(
            "code-123",
            redirect_uri="https://example.test/api/v1/ad-accounts/meta/callback",
            settings=vercel_flag_off_env,
        )

    with pytest.raises(AdConnectionError) as exc_url:
        build_meta_oauth_authorize_url(
            redirect_uri="https://example.test/api/v1/ad-accounts/meta/callback",
            state="state-123",
            settings=vercel_flag_off_env,
        )
    assert exc_url.value.status_code == 404

    with pytest.raises(AdConnectionError) as exc_cb:
        await complete_meta_oauth_callback(
            user_id="user-1",
            code="code-123",
            state="state-123",
            cookie_state="state-123",
            error=None,
            redirect_uri="https://example.test/api/v1/ad-accounts/meta/callback",
            settings=vercel_flag_off_env,
        )
    assert exc_cb.value.status_code == 404


def test_tab_bids_hides_meta_connect_bar_by_default_in_html() -> None:
    """Verify #metaConnectBar is hidden by default in index.html when flag is off."""
    client = TestClient(app)
    html = client.get("/").text
    assert 'id="metaConnectBar" hidden' in html
    assert "info && info.ad_connect_enabled === true" in html
