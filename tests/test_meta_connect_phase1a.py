"""Offline unit, route, security, and real-browser (375px & 1440px) tests for Meta Phase 1a connect.

Covers:
- Meta Graph API version setting (`meta_graph_api_version`, default `v27.0`) and SQL migrations.
- `AD_CONNECT_ENABLED=false` (default): all `/api/v1/ad-accounts/meta/*` routes return 404.
- `MultiFernet` encrypt/decrypt round-trip and comma-separated key rotation (`key_version` 1 -> 2).
- `/connect` redirects to Meta with `ads_read` only and an HMAC-signed user-bound state cookie.
- `/callback` refuses tampered, expired, or cross-user states.
- Token exchange happy path stores ciphertext only (never plaintext).
- `/insights` maps connected insights into `CampaignPerformance`, and Graph code 190 marks the
  connection `'expired'` and tells the UI to reconnect.
- `/disconnect` removes the row and ciphertext; another seller cannot read or disconnect it.
- No token, ciphertext, or app secret ever appears in logs (`caplog`) or HTTP responses.
- Real headless Chromium check at 375px and 1440px for `#tab-bids` with flag off and flag on.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
import uvicorn
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.api.main import REPO_ROOT, app
from src.clients.ad_networks.meta import (
    DEFAULT_META_GRAPH_API_VERSION,
    meta_graph_base_url,
    meta_oauth_dialog_url,
)
from src.clients.supabase import get_supabase_client
from src.config import Settings, get_settings
from src.models.bids import CampaignPerformance
from src.services.ad_connections import (
    AD_OAUTH_STATE_COOKIE,
    AdConnectionError,
    decrypt_token,
    encrypt_token,
    rotate_token_ciphertext,
    sign_meta_oauth_state,
)
from src.services.bid_advisor import compute_metrics

SELLER_A_ID = "11111111-1111-4111-8111-111111111111"
SELLER_A_EMAIL = "seller-a@example.com"
SELLER_A_ACCESS = "jwt-seller-a"

SELLER_B_ID = "22222222-2222-4222-8222-222222222222"
SELLER_B_EMAIL = "seller-b@example.com"
SELLER_B_ACCESS = "jwt-seller-b"

FERNET_KEY_V1 = Fernet.generate_key().decode("ascii")
FERNET_KEY_V2 = Fernet.generate_key().decode("ascii")

NEVER_LOG_SHORT_TOKEN = "EAAB_SHORT_LIVED_SECRET_TOKEN_991122"
NEVER_LOG_LONG_TOKEN = "EAAB_LONG_LIVED_60D_SECRET_TOKEN_334455"
NEVER_LOG_APP_SECRET = "meta_app_secret_super_confidential_778899"

AD_ACCOUNTS_PAYLOAD = {
    "data": [
        {
            "id": "act_1092837465",
            "account_id": "1092837465",
            "name": "Sarabjit Singh Studio Ads",
            "currency": "USD",
            "timezone_name": "America/Los_Angeles",
            "account_status": 1,
        }
    ]
}

INSIGHTS_PAYLOAD = {
    "data": [
        {
            "campaign_id": "1202100001",
            "campaign_name": "Heritage Prints — Prospecting",
            "adset_id": "2303100001",
            "adset_name": "Sikh Heritage Wall Art — Broad US",
            "date_start": "2026-11-15",
            "date_stop": "2026-11-15",
            "impressions": "4000",
            "clicks": "80",
            "spend": "25.00",
            "frequency": "1.20",
            "account_currency": "USD",
            "actions": [{"action_type": "omni_purchase", "value": "3"}],
            "action_values": [{"action_type": "omni_purchase", "value": "150.00"}],
        },
        {
            "campaign_id": "1202100001",
            "campaign_name": "Heritage Prints — Prospecting",
            "adset_id": "2303100001",
            "adset_name": "Sikh Heritage Wall Art — Broad US",
            "date_start": "2026-11-16",
            "date_stop": "2026-11-16",
            "impressions": "4500",
            "clicks": "90",
            "spend": "30.00",
            "frequency": "1.25",
            "account_currency": "USD",
            "actions": [{"action_type": "omni_purchase", "value": "4"}],
            "action_values": [{"action_type": "omni_purchase", "value": "200.00"}],
        },
    ]
}


class FakeAdConnectionsSupabase:
    """In-memory stand-in for Supabase Auth + muse_ad_connection_* service_role RPCs."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {
            SELLER_A_ACCESS: {
                "id": SELLER_A_ID,
                "email": SELLER_A_EMAIL,
                "email_confirmed_at": "2026-11-01T00:00:00Z",
            },
            SELLER_B_ACCESS: {
                "id": SELLER_B_ID,
                "email": SELLER_B_EMAIL,
                "email_confirmed_at": "2026-11-01T00:00:00Z",
            },
        }

    async def auth(
        self,
        path: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        access_token: str | None = None,
        secret: bool = False,
    ) -> dict[str, Any]:
        if path == "user" and access_token in self.users:
            return self.users[access_token]
        from src.clients.supabase import SupabaseError

        raise SupabaseError(401, "Sign in again to continue.")

    async def rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        if name == "muse_ad_connection_upsert":
            uid = str(params["p_user_id"])
            net = str(params["p_network"])
            ext_id = str(params["p_external_account_id"]).strip()
            row = {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "user_id": uid,
                "network": net,
                "external_account_id": ext_id,
                "account_name": params.get("p_account_name") or "",
                "currency": params.get("p_currency") or "USD",
                "timezone_name": params.get("p_timezone_name") or "UTC",
                "scopes": list(params.get("p_scopes") or ["ads_read"]),
                "access_level": "read_only",
                "access_token_ciphertext": params["p_access_token_ciphertext"],
                "refresh_token_ciphertext": params.get("p_refresh_token_ciphertext"),
                "key_version": int(params["p_key_version"]),
                "token_expires_at": params.get("p_token_expires_at"),
                "status": "active",
                "connected_at": "2026-11-19T23:00:00+00:00",
                "updated_at": "2026-11-19T23:00:00+00:00",
                "last_synced_at": None,
            }
            self.rows[(uid, net, ext_id)] = row
            public_copy = {
                k: v
                for k, v in row.items()
                if k not in {"access_token_ciphertext", "refresh_token_ciphertext"}
            }
            return {"allowed": True, "connection": public_copy}

        if name == "muse_ad_connection_list":
            uid = str(params["p_user_id"])
            net = str(params.get("p_network") or "meta")
            items = [
                {
                    k: v
                    for k, v in row.items()
                    if k not in {"access_token_ciphertext", "refresh_token_ciphertext"}
                }
                for (r_uid, r_net, _), row in self.rows.items()
                if r_uid == uid and r_net == net and row["status"] in {"active", "expired"}
            ]
            return {"allowed": True, "connections": items}

        if name == "muse_ad_connection_get":
            uid = str(params["p_user_id"])
            net = str(params["p_network"])
            ext_id = str(params["p_external_account_id"]).strip()
            row = self.rows.get((uid, net, ext_id))
            if not row:
                return {
                    "allowed": False,
                    "status_code": 404,
                    "code": "not_found",
                    "message": "That ad account is not connected to your workspace.",
                }
            return {"allowed": True, "connection": dict(row)}

        if name == "muse_ad_connection_set_status":
            uid = str(params["p_user_id"])
            net = str(params["p_network"])
            ext_id = str(params["p_external_account_id"]).strip()
            row = self.rows.get((uid, net, ext_id))
            if not row:
                return {
                    "allowed": False,
                    "status_code": 404,
                    "code": "not_found",
                    "message": "That ad account is not connected to your workspace.",
                }
            row["status"] = str(params["p_status"])
            return {"allowed": True, "status": row["status"]}

        if name == "muse_ad_connection_disconnect":
            uid = str(params["p_user_id"])
            net = str(params["p_network"])
            ext_id = str(params["p_external_account_id"]).strip()
            if (uid, net, ext_id) not in self.rows:
                return {
                    "allowed": False,
                    "status_code": 404,
                    "code": "not_found",
                    "message": "That ad account is not connected to your workspace.",
                }
            del self.rows[(uid, net, ext_id)]
            return {"allowed": True, "deleted": 1}

        return {"allowed": False, "status_code": 500, "message": f"Unknown RPC {name}"}


def _enable_meta_connect_env(
    monkeypatch: pytest.MonkeyPatch, *, fernet_keys: str = FERNET_KEY_V1
) -> None:
    monkeypatch.setenv("AD_CONNECT_ENABLED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v27.0")
    monkeypatch.setenv("META_APP_ID", "123456789012345")
    monkeypatch.setenv("META_APP_SECRET", NEVER_LOG_APP_SECRET)
    monkeypatch.setenv("AD_TOKEN_ENCRYPTION_KEY", fernet_keys)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("ACCOUNT_COOKIE_SECURE", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_and_clients() -> Iterator[None]:
    get_settings.cache_clear()
    get_supabase_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_supabase_client.cache_clear()


def test_meta_graph_api_version_setting_and_migrations() -> None:
    default_cfg = Settings()
    assert default_cfg.meta_graph_api_version == DEFAULT_META_GRAPH_API_VERSION == "v27.0"
    assert meta_graph_base_url(default_cfg) == "https://graph.facebook.com/v27.0"
    assert meta_oauth_dialog_url(default_cfg) == "https://www.facebook.com/v27.0/dialog/oauth"

    v26_cfg = Settings(meta_graph_api_version="v26.0")
    assert meta_graph_base_url(v26_cfg) == "https://graph.facebook.com/v26.0"
    assert meta_oauth_dialog_url(v26_cfg) == "https://www.facebook.com/v26.0/dialog/oauth"

    migration_sql = (
        REPO_ROOT / "supabase" / "migrations" / "ad_account_connections.sql"
    ).read_text(encoding="utf-8")
    rollback_sql = (
        REPO_ROOT / "supabase" / "migrations" / "ad_account_connections_rollback.sql"
    ).read_text(encoding="utf-8")
    assert "create table if not exists muse_private.ad_account_connections" in migration_sql
    assert "ad_account_audit_log" not in migration_sql.split("begin;", 1)[1]
    assert "enable row level security" in migration_sql
    assert (
        "revoke all on muse_private.ad_account_connections from public, anon, authenticated;"
        in migration_sql
    )
    assert "drop table if exists muse_private.ad_account_connections;" in rollback_sql


def test_flag_off_means_no_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AD_CONNECT_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(app)

    readiness = client.get("/api/v1/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ad_connect_enabled"] is False

    for method, path in (
        ("GET", "/api/v1/ad-accounts/meta/connect"),
        ("POST", "/api/v1/ad-accounts/meta/connect"),
        ("GET", "/api/v1/ad-accounts/meta/callback?code=abc&state=xyz"),
        ("GET", "/api/v1/ad-accounts/meta/accounts"),
        ("GET", "/api/v1/ad-accounts/meta/insights?account_id=act_1092837465"),
        ("POST", "/api/v1/ad-accounts/meta/insights"),
        ("POST", "/api/v1/ad-accounts/meta/disconnect"),
        ("DELETE", "/api/v1/ad-accounts/meta/disconnect?account_id=act_1092837465"),
    ):
        resp = client.request(method, path, follow_redirects=False)
        assert resp.status_code == 404, f"Expected 404 for {method} {path}, got {resp.status_code}"


def test_multifernet_decrypt_round_trip_and_key_rotation() -> None:
    cfg_v1 = Settings(ad_token_encryption_key=FERNET_KEY_V1)
    ciphertext_v1, ver_v1 = encrypt_token(NEVER_LOG_LONG_TOKEN, settings=cfg_v1)
    assert ver_v1 == 1
    assert NEVER_LOG_LONG_TOKEN not in ciphertext_v1
    assert decrypt_token(ciphertext_v1, settings=cfg_v1) == NEVER_LOG_LONG_TOKEN

    # Key rotation: prepend FERNET_KEY_V2 ahead of FERNET_KEY_V1
    cfg_rotated = Settings(ad_token_encryption_key=f"{FERNET_KEY_V2},{FERNET_KEY_V1}")
    # Existing v1 ciphertext still decrypts seamlessly
    assert decrypt_token(ciphertext_v1, settings=cfg_rotated) == NEVER_LOG_LONG_TOKEN

    # New encryptions and rotated ciphertexts use key_version == 2 (FERNET_KEY_V2)
    ciphertext_v2, ver_v2 = encrypt_token(NEVER_LOG_LONG_TOKEN, settings=cfg_rotated)
    assert ver_v2 == 2
    rotated_ct, rotated_ver = rotate_token_ciphertext(ciphertext_v1, settings=cfg_rotated)
    assert rotated_ver == 2

    # Retire FERNET_KEY_V1 completely: v2 and rotated ciphertexts still decrypt, v1 is rejected
    cfg_v2_only = Settings(ad_token_encryption_key=FERNET_KEY_V2)
    assert decrypt_token(ciphertext_v2, settings=cfg_v2_only) == NEVER_LOG_LONG_TOKEN
    assert decrypt_token(rotated_ct, settings=cfg_v2_only) == NEVER_LOG_LONG_TOKEN
    with pytest.raises(AdConnectionError):
        decrypt_token(ciphertext_v1, settings=cfg_v2_only)


def test_connect_redirects_to_meta_with_ads_read_and_signed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sb = FakeAdConnectionsSupabase()
    monkeypatch.setattr("src.services.accounts.get_supabase_client", lambda: fake_sb)
    monkeypatch.setattr("src.services.ad_connections.get_supabase_client", lambda: fake_sb)
    _enable_meta_connect_env(monkeypatch)

    client = TestClient(app)
    # Unauthenticated request is rejected with 401
    unauth = client.get("/api/v1/ad-accounts/meta/connect", follow_redirects=False)
    assert unauth.status_code == 401

    # Authenticated verified seller gets 302 redirect to Meta OAuth with ads_read only
    client.cookies.set("muse_access", SELLER_A_ACCESS)
    resp = client.get("/api/v1/ad-accounts/meta/connect", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    parsed = urlsplit(location)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.facebook.com"
    assert parsed.path == "/v27.0/dialog/oauth"
    params = parse_qs(parsed.query)
    assert params["scope"] == ["ads_read"]
    assert params["client_id"] == ["123456789012345"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"][0].endswith("/api/v1/ad-accounts/meta/callback")
    state_param = params["state"][0]
    assert "." in state_param
    assert resp.cookies.get(AD_OAUTH_STATE_COOKIE) == state_param


def test_callback_refuses_tampered_expired_or_other_users_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sb = FakeAdConnectionsSupabase()
    monkeypatch.setattr("src.services.accounts.get_supabase_client", lambda: fake_sb)
    monkeypatch.setattr("src.services.ad_connections.get_supabase_client", lambda: fake_sb)
    _enable_meta_connect_env(monkeypatch)

    cfg = get_settings()
    client = TestClient(app)
    client.cookies.set("muse_access", SELLER_A_ACCESS)

    # 1. Tampered state signature
    valid_state = sign_meta_oauth_state(SELLER_A_ID, settings=cfg)
    tampered_state = valid_state[:-4] + ("0000" if not valid_state.endswith("0000") else "1111")
    client.cookies.set(AD_OAUTH_STATE_COOKIE, tampered_state)
    tampered_resp = client.get(
        f"/api/v1/ad-accounts/meta/callback?code=auth_code&state={tampered_state}",
        follow_redirects=False,
    )
    assert tampered_resp.status_code == 400
    assert tampered_resp.json()["code"] == "invalid_oauth_state"

    # 2. Expired state (issued 601 seconds ago)
    expired_state = sign_meta_oauth_state(
        SELLER_A_ID,
        now=int(time.time()) - 601,
        settings=cfg,
    )
    client.cookies.set(AD_OAUTH_STATE_COOKIE, expired_state)
    expired_resp = client.get(
        f"/api/v1/ad-accounts/meta/callback?code=auth_code&state={expired_state}",
        follow_redirects=False,
    )
    assert expired_resp.status_code == 400
    assert expired_resp.json()["code"] == "expired_oauth_state"

    # 3. Cross-user state (signed for Seller B, callback invoked by Seller A)
    seller_b_state = sign_meta_oauth_state(SELLER_B_ID, settings=cfg)
    client.cookies.set(AD_OAUTH_STATE_COOKIE, seller_b_state)
    cross_resp = client.get(
        f"/api/v1/ad-accounts/meta/callback?code=auth_code&state={seller_b_state}",
        follow_redirects=False,
    )
    assert cross_resp.status_code == 403
    assert cross_resp.json()["code"] == "cross_user_oauth_state"
    assert fake_sb.rows == {}


def test_token_exchange_stores_ciphertext_only_and_never_logs_or_leaks_tokens(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_sb = FakeAdConnectionsSupabase()
    monkeypatch.setattr("src.services.accounts.get_supabase_client", lambda: fake_sb)
    monkeypatch.setattr("src.services.ad_connections.get_supabase_client", lambda: fake_sb)
    _enable_meta_connect_env(monkeypatch)
    caplog.set_level(logging.DEBUG)

    client = TestClient(app)
    client.cookies.set("muse_access", SELLER_A_ACCESS)

    connect_resp = client.get("/api/v1/ad-accounts/meta/connect", follow_redirects=False)
    state = parse_qs(urlsplit(connect_resp.headers["location"]).query)["state"][0]
    client.cookies.set(AD_OAUTH_STATE_COOKIE, state)

    def _token_handler(request: httpx.Request) -> httpx.Response:
        body_text = request.content.decode("utf-8")
        if "grant_type=fb_exchange_token" in body_text:
            assert f"fb_exchange_token={NEVER_LOG_SHORT_TOKEN}" in body_text
            return httpx.Response(
                200,
                json={
                    "access_token": NEVER_LOG_LONG_TOKEN,
                    "token_type": "bearer",
                    "expires_in": 5184000,
                },
            )
        return httpx.Response(
            200,
            json={
                "access_token": NEVER_LOG_SHORT_TOKEN,
                "token_type": "bearer",
                "expires_in": 3600,
            },
        )

    with respx.mock as router:
        router.post("https://graph.facebook.com/v27.0/oauth/access_token").mock(
            side_effect=_token_handler
        )
        router.get("https://graph.facebook.com/v27.0/me/adaccounts").mock(
            return_value=httpx.Response(200, json=AD_ACCOUNTS_PAYLOAD)
        )
        cb_resp = client.get(
            f"/api/v1/ad-accounts/meta/callback?code=valid_oauth_code&state={state}",
            follow_redirects=False,
        )

    assert cb_resp.status_code == 302
    assert "ad_connect=meta" in cb_resp.headers["location"]

    # Stored row in Supabase contains ciphertext only, never plaintext tokens
    stored_row = fake_sb.rows[(SELLER_A_ID, "meta", "act_1092837465")]
    ct = stored_row["access_token_ciphertext"]
    assert ct != NEVER_LOG_LONG_TOKEN
    assert NEVER_LOG_LONG_TOKEN not in ct
    assert NEVER_LOG_SHORT_TOKEN not in ct
    assert decrypt_token(ct, settings=get_settings()) == NEVER_LOG_LONG_TOKEN

    # Listing connected accounts returns metadata only (no token or ciphertext)
    list_resp = client.get("/api/v1/ad-accounts/meta/accounts")
    assert list_resp.status_code == 200
    body_text = list_resp.text
    assert NEVER_LOG_LONG_TOKEN not in body_text
    assert NEVER_LOG_SHORT_TOKEN not in body_text
    assert ct not in body_text
    accounts = list_resp.json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["external_account_id"] == "act_1092837465"
    assert accounts[0]["account_name"] == "Sarabjit Singh Studio Ads"
    assert accounts[0]["status"] == "active"

    # Assert neither token, ciphertext, nor app secret appeared in any log message
    all_logs = "\n".join(r.getMessage() for r in caplog.records)
    for secret_str in (NEVER_LOG_SHORT_TOKEN, NEVER_LOG_LONG_TOKEN, NEVER_LOG_APP_SECRET, ct):
        assert secret_str not in all_logs
        assert secret_str not in cb_resp.text


def test_insights_maps_to_campaign_performance_and_code_190_marks_expired(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_sb = FakeAdConnectionsSupabase()
    monkeypatch.setattr("src.services.accounts.get_supabase_client", lambda: fake_sb)
    monkeypatch.setattr("src.services.ad_connections.get_supabase_client", lambda: fake_sb)
    _enable_meta_connect_env(monkeypatch)
    caplog.set_level(logging.DEBUG)

    ct, ver = encrypt_token(NEVER_LOG_LONG_TOKEN, settings=get_settings())
    fake_sb.rows[(SELLER_A_ID, "meta", "act_1092837465")] = {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "user_id": SELLER_A_ID,
        "network": "meta",
        "external_account_id": "act_1092837465",
        "account_name": "Sarabjit Singh Studio Ads",
        "currency": "USD",
        "timezone_name": "America/Los_Angeles",
        "scopes": ["ads_read"],
        "access_level": "read_only",
        "access_token_ciphertext": ct,
        "refresh_token_ciphertext": None,
        "key_version": ver,
        "token_expires_at": None,
        "status": "active",
        "connected_at": "2026-11-19T23:00:00+00:00",
        "updated_at": "2026-11-19T23:00:00+00:00",
        "last_synced_at": None,
    }

    client = TestClient(app)
    client.cookies.set("muse_access", SELLER_A_ACCESS)

    # 1. Happy path insights -> CampaignPerformance -> compute_metrics()
    with respx.mock as router:
        router.get("https://graph.facebook.com/v27.0/act_1092837465/insights").mock(
            return_value=httpx.Response(200, json=INSIGHTS_PAYLOAD)
        )
        ok_resp = client.get(
            "/api/v1/ad-accounts/meta/insights"
            "?account_id=act_1092837465&start_date=2026-11-15&end_date=2026-11-16"
        )

    assert ok_resp.status_code == 200
    perf = CampaignPerformance.model_validate(ok_resp.json())
    assert perf.account_name == "Sarabjit Singh Studio Ads"
    assert len(perf.rows) == 2
    metrics = compute_metrics(perf)
    assert metrics.account_totals.spend == 55.0
    assert metrics.account_totals.conversions == 7

    # 2. Expired token (Graph code 190) marks the connection expired and asks to reconnect
    expired_graph_error = {
        "error": {
            "message": "Error validating access token: Session has expired.",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 463,
        }
    }
    with respx.mock as router:
        router.get("https://graph.facebook.com/v27.0/act_1092837465/insights").mock(
            return_value=httpx.Response(401, json=expired_graph_error)
        )
        exp_resp = client.get(
            "/api/v1/ad-accounts/meta/insights"
            "?account_id=act_1092837465&start_date=2026-11-15&end_date=2026-11-16"
        )

    assert exp_resp.status_code == 401
    exp_json = exp_resp.json()
    assert exp_json["code"] == "meta_token_expired"
    assert exp_json["reconnect_required"] is True
    assert "Reconnect Meta Ads" in exp_json["detail"]
    assert fake_sb.rows[(SELLER_A_ID, "meta", "act_1092837465")]["status"] == "expired"

    all_logs = "\n".join(r.getMessage() for r in caplog.records)
    assert NEVER_LOG_LONG_TOKEN not in all_logs
    assert NEVER_LOG_LONG_TOKEN not in exp_resp.text
    assert ct not in exp_resp.text


def test_disconnect_removes_ciphertext_and_blocks_cross_seller_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sb = FakeAdConnectionsSupabase()
    monkeypatch.setattr("src.services.accounts.get_supabase_client", lambda: fake_sb)
    monkeypatch.setattr("src.services.ad_connections.get_supabase_client", lambda: fake_sb)
    _enable_meta_connect_env(monkeypatch)

    ct, ver = encrypt_token(NEVER_LOG_LONG_TOKEN, settings=get_settings())
    fake_sb.rows[(SELLER_A_ID, "meta", "act_1092837465")] = {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "user_id": SELLER_A_ID,
        "network": "meta",
        "external_account_id": "act_1092837465",
        "account_name": "Sarabjit Singh Studio Ads",
        "currency": "USD",
        "timezone_name": "America/Los_Angeles",
        "scopes": ["ads_read"],
        "access_level": "read_only",
        "access_token_ciphertext": ct,
        "refresh_token_ciphertext": None,
        "key_version": ver,
        "token_expires_at": None,
        "status": "active",
        "connected_at": "2026-11-19T23:00:00+00:00",
        "updated_at": "2026-11-19T23:00:00+00:00",
        "last_synced_at": None,
    }

    client = TestClient(app)

    # Seller B cannot list, read insights from, or disconnect Seller A's connection
    client.cookies.set("muse_access", SELLER_B_ACCESS)
    b_list = client.get("/api/v1/ad-accounts/meta/accounts")
    assert b_list.status_code == 200
    assert b_list.json()["accounts"] == []

    b_insights = client.get("/api/v1/ad-accounts/meta/insights?account_id=act_1092837465")
    assert b_insights.status_code == 404

    b_disconnect = client.post(
        "/api/v1/ad-accounts/meta/disconnect",
        json={"account_id": "act_1092837465"},
    )
    assert b_disconnect.status_code == 404
    assert (SELLER_A_ID, "meta", "act_1092837465") in fake_sb.rows

    # Seller A disconnects their own connection: row and ciphertext are deleted
    client.cookies.set("muse_access", SELLER_A_ACCESS)
    a_disconnect = client.post(
        "/api/v1/ad-accounts/meta/disconnect",
        json={"account_id": "act_1092837465"},
    )
    assert a_disconnect.status_code == 200
    assert a_disconnect.json() == {"disconnected": True, "account_id": "act_1092837465"}
    assert (SELLER_A_ID, "meta", "act_1092837465") not in fake_sb.rows

    a_list = client.get("/api/v1/ad-accounts/meta/accounts")
    assert a_list.json()["accounts"] == []
    a_insights = client.get("/api/v1/ad-accounts/meta/insights?account_id=act_1092837465")
    assert a_insights.status_code == 404
    get_supabase_client.cache_clear()


@pytest.fixture(scope="module")
def live_server_url() -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def _find_playwright_python() -> str | None:
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3") or ""):
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run(
            [candidate, "-c", "import playwright.sync_api"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return None


def test_tab_bids_browser_375_and_1440_flag_off_and_on(live_server_url: str) -> None:
    """Verify #tab-bids in a real Chromium browser at 375px and 1440px with flag off and on."""
    pw_python = _find_playwright_python()
    if not pw_python:
        pytest.skip("Playwright is not available in any Python interpreter.")

    script = textwrap.dedent(
        f"""
        import json
        from playwright.sync_api import sync_playwright

        BASE = {live_server_url!r}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (375, 1440):
                    # 1. Flag OFF (default server response: ad_connect_enabled=false)
                    ctx_off = browser.new_context(viewport={{"width": width, "height": 900}})
                    page_off = ctx_off.new_page()
                    errors_off = []
                    page_off.on("pageerror", lambda e: errors_off.append(str(e)))
                    page_off.goto(f"{{BASE}}/#tab-bids", wait_until="networkidle")
                    page_off.locator("#tab-bids").wait_for(state="visible", timeout=5000)

                    assert not page_off.locator("#metaConnectBar").is_visible(), (
                        f"metaConnectBar must be hidden when flag is off at {{width}}px"
                    )
                    assert page_off.locator("#runBidsBtn").is_visible()
                    assert page_off.locator("#csvUploadLabel").is_visible()
                    overflow_off = page_off.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth + 1"
                    )
                    assert not overflow_off, f"Horizontal overflow with flag off at {{width}}px"
                    assert not errors_off, (
                        f"Page errors with flag off at {{width}}px: {{errors_off}}"
                    )
                    ctx_off.close()

                    # 2. Flag ON (route-mocked ad_connect_enabled=true)
                    ctx_on = browser.new_context(viewport={{"width": width, "height": 900}})
                    page_on = ctx_on.new_page()
                    errors_on = []
                    page_on.on("pageerror", lambda e: errors_on.append(str(e)))

                    page_on.route(
                        "**/api/v1/readiness",
                        lambda route: route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({{
                                "default_mode": "saved",
                                "live_unlock_configured": False,
                                "provider_key_configured": False,
                                "provider_verified": False,
                                "accounts_required": False,
                                "accounts_configured": True,
                                "ad_connect_enabled": True,
                                "trial_runs": 3,
                            }}),
                        ),
                    )
                    page_on.route(
                        "**/api/v1/ad-accounts/meta/accounts",
                        lambda route: route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps({{
                                "enabled": True,
                                "network": "meta",
                                "accounts": [
                                    {{
                                        "external_account_id": "act_1092837465",
                                        "network": "meta",
                                        "account_name": "Sarabjit Singh Studio Ads",
                                        "currency": "USD",
                                        "timezone_name": "America/Los_Angeles",
                                        "status": "active",
                                    }}
                                ],
                            }}),
                        ),
                    )
                    page_on.route(
                        "**/api/v1/ad-accounts/meta/insights*",
                        lambda route: route.fulfill(
                            status=401,
                            content_type="application/json",
                            body=json.dumps({{
                                "detail": (
                                    "Your Meta Ads token expired. Reconnect Meta Ads "
                                    "to refresh your campaign performance."
                                ),
                                "code": "meta_token_expired",
                                "reconnect_required": True,
                                "account_id": "act_1092837465",
                            }}),
                        ),
                    )
                    page_on.route(
                        "**/api/v1/ad-accounts/meta/disconnect",
                        lambda route: route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {{"disconnected": True, "account_id": "act_1092837465"}}
                            ),
                        ),
                    )

                    page_on.goto(f"{{BASE}}/#tab-bids", wait_until="networkidle")
                    page_on.locator("#metaConnectBar").wait_for(state="visible", timeout=5000)
                    assert page_on.locator("#connectMetaAdsBtn").is_visible()
                    assert page_on.locator("#metaAdAccountSelect").is_visible()
                    assert page_on.locator("#loadMetaInsightsBtn").is_visible()
                    assert page_on.locator("#disconnectMetaAdsBtn").is_visible()

                    overflow_on = page_on.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth + 1"
                    )
                    assert not overflow_on, f"Horizontal overflow with flag on at {{width}}px"

                    # Trigger expired token (code 190) response and verify UI prompts to reconnect
                    page_on.locator("#loadMetaInsightsBtn").click()
                    page_on.wait_for_function(
                        "document.getElementById('connectMetaAdsBtn')"
                        ".textContent.includes('Reconnect Meta Ads')"
                    )
                    status_text = page_on.locator("#metaConnectStatus").text_content() or ""
                    assert "expired" in status_text.lower() and "reconnect" in status_text.lower()

                    # Trigger disconnect and verify account picker hides
                    page_on.locator("#disconnectMetaAdsBtn").click()
                    page_on.wait_for_function(
                        "document.getElementById('metaAdAccountSelectWrap').hidden === true"
                    )
                    assert not errors_on, f"Page errors with flag on at {{width}}px: {{errors_on}}"
                    ctx_on.close()
            finally:
                browser.close()
        """
    )
    proc = subprocess.run(
        [pw_python, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Playwright browser verification failed:\n{proc.stderr}\n{proc.stdout}"
    )
