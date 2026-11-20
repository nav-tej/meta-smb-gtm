"""Encrypted token vault and OAuth state verification for connected seller ad accounts.

Security invariants:
- OAuth tokens are encrypted in Python using `cryptography.fernet.MultiFernet` before reaching
  Supabase (`muse_private.ad_account_connections`, accessed exclusively via `service_role` RPCs).
- `AD_TOKEN_ENCRYPTION_KEY` accepts comma-separated Fernet keys (newest key first) for key
  rotation, recording `key_version` on every stored row.
- OAuth `state` tokens are HMAC-SHA256 signed, stored in an HttpOnly cookie, bound to the
  authenticated `user_id`, and expire after 10 minutes.
- Plaintext tokens, ciphertexts, and encryption keys never appear in logs, exception messages,
  or API response models.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import BaseModel, ConfigDict, Field

from src.clients.ad_networks.base import (
    AdAccountSummary,
    AdNetworkAuthError,
    AdNetworkDisabledError,
    AdNetworkError,
)
from src.clients.ad_networks.meta import (
    MetaAdsReadClient,
    exchange_meta_oauth_code,
    meta_oauth_dialog_url,
    normalize_meta_account_id,
)
from src.clients.supabase import SupabaseClient, SupabaseError, get_supabase_client
from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

AD_OAUTH_STATE_COOKIE = "muse_ad_oauth_state"
AD_OAUTH_STATE_TTL_SECONDS = 600
META_READ_ONLY_SCOPE = "ads_read"
SAFE_AD_RETURN_PATHS = frozenset({"/#tab-bids", "/", "/first-ad"})


class AdConnectionError(Exception):
    """Sanitized ad-connection error safe to surface in HTTP responses."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        code: str = "ad_connection_error",
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code


class AdConnectionSummary(BaseModel):
    """Seller-facing metadata for a connected ad account (never carries tokens or ciphertexts)."""

    model_config = ConfigDict(extra="ignore")

    external_account_id: str = Field(min_length=1)
    network: Literal["meta", "google_ads", "tiktok", "x", "linkedin"] = "meta"
    account_name: str = ""
    currency: str = Field(default="USD", min_length=3, max_length=3)
    timezone_name: str = "UTC"
    scopes: list[str] = Field(default_factory=lambda: [META_READ_ONLY_SCOPE])
    access_level: Literal["read_only", "paused_drafts"] = "read_only"
    status: Literal["active", "expired", "revoked", "disconnected"] = "active"
    key_version: int = Field(default=1, ge=1)
    token_expires_at: str | None = None
    connected_at: str | None = None
    updated_at: str | None = None
    last_synced_at: str | None = None


def safe_ad_return_path(next_path: str | None) -> str:
    """Restrict post-OAuth redirects to known internal ad advisor views."""
    candidate = (next_path or "").strip()
    return candidate if candidate in SAFE_AD_RETURN_PATHS else "/#tab-bids"


def _parse_encryption_keys(settings: Settings | None = None) -> tuple[MultiFernet, int]:
    """Build a `MultiFernet` from comma-separated `AD_TOKEN_ENCRYPTION_KEY` (newest first).

    Each entry may be either a bare 44-char Fernet key or `<version>:<fernet_key>`. When bare
    keys are used, `key_version` equals the number of comma-separated keys so prepending a new
    rotated key increments `key_version` deterministically (1 -> 2 -> 3).
    """
    cfg = settings or get_settings()
    raw = cfg.ad_token_encryption_key.strip()
    if not raw:
        raise AdConnectionError(
            503,
            "Meta Ads connection is not available right now. Please try again later.",
            code="encryption_not_configured",
        )

    entries = [part.strip() for part in raw.split(",") if part.strip()]
    if not entries:
        raise AdConnectionError(
            503,
            "Meta Ads connection is not available right now. Please try again later.",
            code="encryption_not_configured",
        )

    fernets: list[Fernet] = []
    explicit_primary_version: int | None = None
    for idx, entry in enumerate(entries):
        key_str = entry
        if ":" in entry:
            ver_part, candidate_key = entry.split(":", 1)
            if ver_part.strip().isdigit() and int(ver_part.strip()) >= 1:
                if idx == 0:
                    explicit_primary_version = int(ver_part.strip())
                key_str = candidate_key.strip()
        try:
            fernets.append(Fernet(key_str.encode("ascii")))
        except (ValueError, TypeError) as err:
            raise AdConnectionError(
                503,
                "Meta Ads connection is not available right now. Please try again later.",
                code="encryption_key_invalid",
            ) from err

    primary_version = (
        explicit_primary_version if explicit_primary_version is not None else len(fernets)
    )
    return MultiFernet(fernets), primary_version


def encrypt_token(
    plaintext: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, int]:
    """Encrypt an OAuth token with the primary Fernet key and return `(ciphertext, key_version)`."""
    cleaned = plaintext.strip()
    if not cleaned:
        raise ValueError("Cannot encrypt an empty OAuth token.")
    multi, version = _parse_encryption_keys(settings)
    token_bytes = multi.encrypt(cleaned.encode("utf-8"))
    return token_bytes.decode("ascii"), version


def decrypt_token(
    ciphertext: str,
    *,
    settings: Settings | None = None,
) -> str:
    """Decrypt a stored token ciphertext across any active or historical key in `MultiFernet`."""
    cleaned = ciphertext.strip()
    if not cleaned:
        raise AdConnectionError(
            401,
            "Your Meta Ads connection expired. Reconnect to load your latest results.",
            code="token_missing",
        )
    multi, _ = _parse_encryption_keys(settings)
    try:
        plaintext_bytes = multi.decrypt(cleaned.encode("ascii"))
    except (InvalidToken, ValueError) as err:
        raise AdConnectionError(
            401,
            "Your Meta Ads connection expired. Reconnect to load your latest results.",
            code="token_decrypt_failed",
        ) from err
    return plaintext_bytes.decode("utf-8")


def rotate_token_ciphertext(
    ciphertext: str,
    *,
    settings: Settings | None = None,
) -> tuple[str, int]:
    """Re-encrypt an existing ciphertext under the newest primary key in `MultiFernet`."""
    cleaned = ciphertext.strip()
    if not cleaned:
        raise ValueError("Cannot rotate an empty ciphertext.")
    multi, version = _parse_encryption_keys(settings)
    try:
        rotated_bytes = multi.rotate(cleaned.encode("ascii"))
    except (InvalidToken, ValueError) as err:
        raise AdConnectionError(
            401,
            "Your Meta Ads connection expired. Reconnect to load your latest results.",
            code="token_rotate_failed",
        ) from err
    return rotated_bytes.decode("ascii"), version


def _state_signing_key(settings: Settings | None = None) -> bytes:
    cfg = settings or get_settings()
    raw_secret = (
        cfg.ad_token_encryption_key.strip()
        or cfg.meta_app_secret.strip()
        or cfg.supabase_secret_key.strip()
    )
    if not raw_secret:
        raise AdConnectionError(
            503,
            "Meta Ads connection is not available right now. Please try again later.",
            code="oauth_not_configured",
        )
    return hashlib.sha256(f"muse-ad-oauth-state:{raw_secret}".encode()).digest()


def sign_meta_oauth_state(
    user_id: str,
    *,
    next_path: str | None = "/#tab-bids",
    now: int | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a 10-minute HMAC-signed OAuth state token bound to `user_id`."""
    canonical_uid = str(UUID(str(user_id)))
    ts = int(now if now is not None else time.time())
    payload = json.dumps(
        {
            "uid": canonical_uid,
            "net": "meta",
            "next": safe_ad_return_path(next_path),
            "ts": ts,
            "nonce": secrets.token_hex(16),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(
        _state_signing_key(settings), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{sig}"


def verify_meta_oauth_state(
    state: str | None,
    cookie_state: str | None,
    *,
    current_user_id: str,
    now: int | None = None,
    settings: Settings | None = None,
) -> str:
    """Verify OAuth state matches the cookie, HMAC signature, expiry, and `current_user_id`."""
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise AdConnectionError(
            400,
            (
                "That Meta Ads connection request expired or did not match this browser. "
                "Please try again."
            ),
            code="invalid_oauth_state",
        )
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise AdConnectionError(
            400,
            "We could not confirm that Meta Ads connection request. Please try again.",
            code="invalid_oauth_state",
        )
    encoded, sig = parts
    expected_sig = hmac.new(
        _state_signing_key(settings),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise AdConnectionError(
            400,
            "We could not confirm that Meta Ads connection request. Please try again.",
            code="invalid_oauth_state",
        )
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(data, dict) or data.get("net") != "meta":
            raise ValueError("wrong network")
        issued_ts = int(data["ts"])
        state_uid = str(UUID(str(data["uid"])))
        expected_uid = str(UUID(str(current_user_id)))
    except (KeyError, ValueError, TypeError) as err:
        raise AdConnectionError(
            400,
            "We could not confirm that Meta Ads connection request. Please try again.",
            code="invalid_oauth_state",
        ) from err

    if not hmac.compare_digest(state_uid, expected_uid):
        raise AdConnectionError(
            403,
            (
                "That Meta Ads connection was started from a different Muse account. "
                "Try again from this account."
            ),
            code="cross_user_oauth_state",
        )

    current_ts = int(now if now is not None else time.time())
    if current_ts - issued_ts > AD_OAUTH_STATE_TTL_SECONDS or issued_ts - current_ts > 60:
        raise AdConnectionError(
            400,
            "That connection request timed out. Try connecting Meta Ads again.",
            code="expired_oauth_state",
        )
    return safe_ad_return_path(data.get("next"))


def build_meta_oauth_authorize_url(
    *,
    redirect_uri: str,
    state: str,
    settings: Settings | None = None,
) -> str:
    """Build the Facebook Login for Business dialog URL.

    When `meta_login_config_id` is set, sends `config_id` and omits `scope` as recommended by
    Meta's Facebook Login for Business documentation. When empty, falls back to `scope=ads_read`.
    """
    cfg = settings or get_settings()
    if not cfg.ad_connect_enabled:
        raise AdConnectionError(404, "Ad account connections are disabled.", code="disabled")
    app_id = cfg.meta_app_id.strip()
    app_secret = cfg.meta_app_secret.strip()
    if not app_id or not app_secret:
        raise AdConnectionError(
            503,
            "Meta Ads connection is not available right now. Please try again later.",
            code="meta_app_not_configured",
        )
    # Validate that token encryption is ready before sending the seller to Meta.
    _parse_encryption_keys(cfg)

    dialog_url = meta_oauth_dialog_url(cfg)
    params: dict[str, str] = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    config_id = cfg.meta_login_config_id.strip()
    if config_id:
        params["config_id"] = config_id
    else:
        params["scope"] = META_READ_ONLY_SCOPE
    params["state"] = state
    return f"{dialog_url}?{urlencode(params)}"


async def _rpc(
    name: str,
    params: dict[str, Any],
    *,
    supabase_client: SupabaseClient | None = None,
) -> dict[str, Any]:
    client = supabase_client or get_supabase_client()
    try:
        result = await client.rpc(name, params)
    except SupabaseError as err:
        raise AdConnectionError(
            503,
            "Ad account storage is unavailable right now. Please try again shortly.",
            code="storage_unavailable",
        ) from err
    if result.get("allowed") is not True:
        status = result.get("status_code")
        code = str(result.get("code") or "ad_connection_error")
        msg = str(result.get("message") or "Could not update ad account connection.")[:200]
        raise AdConnectionError(
            int(status) if isinstance(status, int) and status in {400, 403, 404, 409, 422} else 503,
            msg,
            code=code,
        )
    return result


async def save_meta_connection(
    user_id: str,
    account: AdAccountSummary,
    *,
    access_token: str,
    expires_in_seconds: int | None = None,
    scopes: tuple[str, ...] = (META_READ_ONLY_SCOPE,),
    settings: Settings | None = None,
    supabase_client: SupabaseClient | None = None,
    now: datetime | None = None,
) -> AdConnectionSummary:
    """Encrypt `access_token` with `MultiFernet` and persist via `service_role` RPC."""
    canonical_uid = str(UUID(str(user_id)))
    act_id = normalize_meta_account_id(account.account_id)
    ciphertext, key_version = encrypt_token(access_token, settings=settings)

    expires_at_iso: str | None = None
    if expires_in_seconds is not None and expires_in_seconds > 0:
        ref_now = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at_iso = (ref_now + timedelta(seconds=expires_in_seconds)).isoformat()

    result = await _rpc(
        "muse_ad_connection_upsert",
        {
            "p_user_id": canonical_uid,
            "p_network": "meta",
            "p_external_account_id": act_id,
            "p_account_name": account.name,
            "p_currency": account.currency,
            "p_timezone_name": account.timezone_name,
            "p_scopes": list(scopes),
            "p_access_token_ciphertext": ciphertext,
            "p_refresh_token_ciphertext": None,
            "p_key_version": key_version,
            "p_token_expires_at": expires_at_iso,
        },
        supabase_client=supabase_client,
    )
    conn_obj = result.get("connection")
    if not isinstance(conn_obj, dict):
        raise AdConnectionError(503, "Ad account storage returned an invalid connection record.")
    return AdConnectionSummary.model_validate(conn_obj)


async def list_meta_connections(
    user_id: str,
    *,
    supabase_client: SupabaseClient | None = None,
) -> list[AdConnectionSummary]:
    """List a seller's connected Meta ad accounts (metadata only, no tokens or ciphertexts)."""
    canonical_uid = str(UUID(str(user_id)))
    result = await _rpc(
        "muse_ad_connection_list",
        {"p_user_id": canonical_uid, "p_network": "meta"},
        supabase_client=supabase_client,
    )
    raw_list = result.get("connections")
    if not isinstance(raw_list, list):
        return []
    summaries: list[AdConnectionSummary] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        owner = item.get("user_id")
        if owner is not None and str(UUID(str(owner))) != canonical_uid:
            continue
        summaries.append(AdConnectionSummary.model_validate(item))
    return summaries


async def load_meta_connection(
    user_id: str,
    external_account_id: str,
    *,
    settings: Settings | None = None,
    supabase_client: SupabaseClient | None = None,
) -> tuple[AdConnectionSummary, str]:
    """Load and decrypt a seller's Meta ad account token, verifying row ownership."""
    canonical_uid = str(UUID(str(user_id)))
    try:
        act_id = normalize_meta_account_id(external_account_id)
    except ValueError as err:
        raise AdConnectionError(422, "Enter a valid Meta ad account ID.") from err

    result = await _rpc(
        "muse_ad_connection_get",
        {
            "p_user_id": canonical_uid,
            "p_network": "meta",
            "p_external_account_id": act_id,
        },
        supabase_client=supabase_client,
    )
    conn_obj = result.get("connection")
    if not isinstance(conn_obj, dict):
        raise AdConnectionError(
            404,
            "That ad account is not connected to your workspace.",
            code="not_found",
        )
    owner = conn_obj.get("user_id")
    if owner is None or not hmac.compare_digest(str(UUID(str(owner))), canonical_uid):
        raise AdConnectionError(
            404,
            "That ad account is not connected to your workspace.",
            code="not_found",
        )
    ciphertext = str(conn_obj.get("access_token_ciphertext") or "")
    token = decrypt_token(ciphertext, settings=settings)
    summary = AdConnectionSummary.model_validate(conn_obj)
    return summary, token


async def mark_meta_connection_status(
    user_id: str,
    external_account_id: str,
    *,
    status: Literal["active", "expired", "revoked"],
    supabase_client: SupabaseClient | None = None,
) -> None:
    """Update a seller's Meta connection status (e.g. `'expired'` on Graph code 190)."""
    canonical_uid = str(UUID(str(user_id)))
    act_id = normalize_meta_account_id(external_account_id)
    await _rpc(
        "muse_ad_connection_set_status",
        {
            "p_user_id": canonical_uid,
            "p_network": "meta",
            "p_external_account_id": act_id,
            "p_status": status,
        },
        supabase_client=supabase_client,
    )


async def disconnect_meta_connection(
    user_id: str,
    external_account_id: str,
    *,
    supabase_client: SupabaseClient | None = None,
) -> None:
    """Delete a seller's connected Meta ad account row and its encrypted token ciphertext."""
    canonical_uid = str(UUID(str(user_id)))
    try:
        act_id = normalize_meta_account_id(external_account_id)
    except ValueError as err:
        raise AdConnectionError(422, "Enter a valid Meta ad account ID.") from err

    await _rpc(
        "muse_ad_connection_disconnect",
        {
            "p_user_id": canonical_uid,
            "p_network": "meta",
            "p_external_account_id": act_id,
        },
        supabase_client=supabase_client,
    )


async def complete_meta_oauth_callback(
    *,
    user_id: str,
    code: str | None,
    state: str | None,
    cookie_state: str | None,
    error: str | None,
    redirect_uri: str,
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
    supabase_client: SupabaseClient | None = None,
) -> tuple[str, list[AdConnectionSummary]]:
    """Verify OAuth state, exchange code for long-lived token, and save encrypted connections."""
    cfg = settings or get_settings()
    if not cfg.ad_connect_enabled:
        raise AdConnectionError(404, "Ad account connections are disabled.", code="disabled")
    if error:
        raise AdConnectionError(
            400,
            "You cancelled connecting Meta Ads. Nothing was saved.",
            code="oauth_denied",
        )
    target = verify_meta_oauth_state(
        state,
        cookie_state,
        current_user_id=user_id,
        settings=cfg,
    )
    if not code or not code.strip():
        raise AdConnectionError(
            400,
            "We could not confirm that Meta Ads connection request. Please try again.",
            code="missing_code",
        )

    try:
        access_token, expires_in = await exchange_meta_oauth_code(
            code,
            redirect_uri=redirect_uri,
            settings=cfg,
            http_client=http_client,
        )
        read_client = MetaAdsReadClient(
            access_token=access_token,
            settings=cfg,
            http_client=http_client,
        )
        try:
            accounts = await read_client.list_ad_accounts()
        finally:
            await read_client.aclose()
    except AdNetworkDisabledError as err:
        raise AdConnectionError(
            404, "Ad account connections are disabled.", code="disabled"
        ) from err
    except AdNetworkAuthError as err:
        raise AdConnectionError(
            401,
            (
                "We could not finish connecting Meta Ads right now. "
                "Nothing was saved; please try again."
            ),
            code="meta_oauth_failed",
        ) from err
    except AdNetworkError as err:
        raise AdConnectionError(
            502,
            "Could not reach Meta to list your ad accounts. Please try again.",
            code="meta_upstream_error",
        ) from err

    if not accounts:
        raise AdConnectionError(
            422,
            "No Meta ad accounts were found on that Facebook profile.",
            code="no_ad_accounts",
        )

    saved: list[AdConnectionSummary] = []
    for account in accounts:
        summary = await save_meta_connection(
            user_id,
            account,
            access_token=access_token,
            expires_in_seconds=expires_in,
            scopes=(META_READ_ONLY_SCOPE,),
            settings=cfg,
            supabase_client=supabase_client,
        )
        saved.append(summary)
    return target, saved
