"""Production's env shape keeps Meta ad connections fully off.

On Nov 20, 2026 production and preview have META_APP_ID and META_APP_SECRET set, but no
AD_CONNECT_ENABLED, AD_TOKEN_ENCRYPTION_KEY, META_LOGIN_CONFIG_ID or META_ADS_ACCESS_TOKEN, and the
ad_account_connections migration is not applied. With that shape every ad-account route must stay
a 404 (a cancel callback must not redirect), the routes must stay out of the API schema, the
readiness check must say the feature is off, and nothing may reach the token store or Meta.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.api.main import app
from src.clients.supabase import get_supabase_client
from src.config import get_settings
from src.services import ad_connections

PLACEHOLDER_SECRET = "placeholder-app-secret-not-real-0000"
ROUTES = (
    ("GET", "/api/v1/ad-accounts/meta/connect"),
    ("POST", "/api/v1/ad-accounts/meta/connect"),
    ("GET", "/api/v1/ad-accounts/meta/callback?code=abc&state=xyz"),
    ("GET", "/api/v1/ad-accounts/meta/callback?error=access_denied&state=xyz"),
    ("GET", "/api/v1/ad-accounts/meta/callback"),
    ("GET", "/api/v1/ad-accounts/meta/accounts"),
    ("GET", "/api/v1/ad-accounts/meta/insights?account_id=act_1092837465"),
    ("POST", "/api/v1/ad-accounts/meta/insights"),
    ("POST", "/api/v1/ad-accounts/meta/disconnect"),
    ("DELETE", "/api/v1/ad-accounts/meta/disconnect?account_id=act_1092837465"),
)


@pytest.fixture(autouse=True)
def _production_shape(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (
        "AD_CONNECT_ENABLED",
        "AD_TOKEN_ENCRYPTION_KEY",
        "META_LOGIN_CONFIG_ID",
        "META_ADS_ACCESS_TOKEN",
        "META_AD_ACCOUNT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("META_APP_ID", "1113987174851049")
    monkeypatch.setenv("META_APP_SECRET", PLACEHOLDER_SECRET)
    get_settings.cache_clear()
    get_supabase_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_supabase_client.cache_clear()


def test_production_env_shape_keeps_ad_connections_off(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert settings.ad_connect_enabled is False
    assert settings.meta_app_id and settings.meta_app_secret

    rpc_calls: list[str] = []

    async def no_rpc(*args: object, **kwargs: object) -> object:
        rpc_calls.append(str(args[:1]))
        raise AssertionError("the token store was called with the flag off")

    monkeypatch.setattr(ad_connections, "_rpc", no_rpc)
    client = TestClient(app)
    with respx.mock(assert_all_called=False) as network:
        outbound = network.route().mock(return_value=httpx.Response(500))
        for method, path in ROUTES:
            resp = client.request(method, path, follow_redirects=False)
            assert resp.status_code == 404, f"{method} {path} -> {resp.status_code}"
            assert "location" not in resp.headers, f"{method} {path} redirected"
            assert PLACEHOLDER_SECRET not in resp.text
        readiness = client.get("/api/v1/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["ad_connect_enabled"] is False
        assert PLACEHOLDER_SECRET not in readiness.text
        assert "1113987174851049" not in readiness.text
        assert outbound.call_count == 0, [str(call.request.url) for call in outbound.calls]
    assert rpc_calls == []

    schema_paths = app.openapi()["paths"]
    assert not [p for p in schema_paths if p.startswith("/api/v1/ad-accounts")]

    # The bid tab's connect bar ships hidden and only opens when readiness says the flag is on.
    home = client.get("/")
    assert home.status_code == 200
    assert '<div id="metaConnectBar" hidden' in home.text
    assert "metaConnectState.enabled = info && info.ad_connect_enabled === true;" in home.text
