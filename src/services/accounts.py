"""Verified account sessions and creator-owned workspace persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, Response

from src.clients.supabase import SupabaseError, configured, get_supabase_client
from src.config import get_settings

SAFE_NEXT_PATHS = {"/", "/account", "/today", "/create", "/digest", "/portal"}


@dataclass(frozen=True)
class AccountSession:
    user_id: str
    email: str
    email_verified: bool
    access_token: str
    session_id: str | None


def safe_next_path(next_path: str | None) -> str:
    """Restrict post-auth redirects to known internal routes."""
    candidate = (next_path or "").strip()
    return candidate if candidate in SAFE_NEXT_PATHS else "/account"


def request_base_url(request: Request) -> str:
    """Resolve the trusted base URL for the current deployment."""
    settings = get_settings()
    default_base = getattr(settings, "app_url", "https://meta-smb-gtm.vercel.app").rstrip("/")
    req_host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host") or "")
        .split(",", 1)[0]
        .strip()
        .lower()
    )
    if req_host and req_host.endswith(".vercel.app"):
        return f"https://{req_host}"
    if not getattr(settings, "hosted_environment", True) and req_host.startswith(
        ("localhost", "127.0.0.1")
    ):
        scheme = (
            (request.headers.get("x-forwarded-proto") or request.url.scheme or "http")
            .split(",", 1)[0]
            .strip()
        )
        return f"{scheme}://{req_host}"
    return default_base


def trusted_mutation(request: Request) -> None:
    """Reject cross-site cookie mutations, including login and callback injection."""
    settings = get_settings()
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    app = urlsplit(getattr(settings, "app_url", "https://meta-smb-gtm.vercel.app"))
    valid = bool(origin) and origin == f"{app.scheme}://{app.netloc}"
    req_host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host") or "")
        .split(",", 1)[0]
        .strip()
        .lower()
    )
    if (
        not valid
        and parsed.scheme == "https"
        and parsed.netloc
        and parsed.netloc.lower() == req_host
        and parsed.netloc.lower().endswith(".vercel.app")
    ):
        valid = True
    if not settings.hosted_environment:
        valid = valid or (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )
    if not valid:
        raise HTTPException(403, "Open Muse in its own tab to manage your account.")
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "Send account requests as JSON.")


def clear_cookies(response: Response) -> None:
    """Remove the two HttpOnly session cookies."""
    for name in ("muse_access", "muse_refresh"):
        response.delete_cookie(
            name,
            path="/",
            secure=getattr(get_settings(), "account_cookie_secure", True),
            httponly=True,
            samesite="lax",
        )


def set_cookies(response: Response, tokens: dict[str, Any]) -> None:
    """Keep authentication credentials out of browser JavaScript and response JSON."""
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str):
        raise SupabaseError(503, "Account service returned an invalid session.")
    if not access or not refresh or len(access) > 12000 or len(refresh) > 12000:
        raise SupabaseError(503, "Account service returned an invalid session.")
    expires = tokens.get("expires_in", 3600)
    expires = max(60, min(expires, 86400)) if isinstance(expires, int) else 3600
    for name, value, age in (
        ("muse_access", access, expires),
        ("muse_refresh", refresh, 30 * 86400),
    ):
        response.set_cookie(
            name,
            value,
            max_age=age,
            secure=getattr(get_settings(), "account_cookie_secure", True),
            httponly=True,
            samesite="lax",
            path="/",
        )


async def verify_token(access_token: str) -> AccountSession:
    """Always verify with GetUser before considering any JWT claim."""
    user = await get_supabase_client().auth("user", access_token=access_token)
    try:
        user_id = str(UUID(user["id"]))
        email = user["email"]
        if not isinstance(email, str) or not email or user.get("is_anonymous"):
            raise ValueError("Missing account email")
        if user.get("banned_until"):
            raise SupabaseError(403, "This account is suspended.")
    except (KeyError, ValueError, TypeError) as err:
        raise SupabaseError(401, "Sign in again to continue.") from err
    session_id = None
    try:
        payload = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        session_id = str(UUID(claims["session_id"]))
    except (IndexError, KeyError, ValueError, TypeError):
        pass
    verified = bool(
        user.get("email_confirmed_at") or (user.get("user_metadata") or {}).get("email_verified")
    )
    return AccountSession(user_id, email, verified, access_token, session_id)


async def resolve_account(
    request: Request, response: Response | None = None, require_verified: bool = False
) -> AccountSession | None:
    """Resolve cookies against Supabase, optionally refresh, and require verification."""
    account = None
    access = request.cookies.get("muse_access")
    refresh = request.cookies.get("muse_refresh")
    try:
        if access:
            try:
                account = await verify_token(access)
            except SupabaseError as err:
                if err.status_code != 401:
                    raise
        if account is None and refresh and response is not None:
            tokens = await get_supabase_client().auth(
                "token?grant_type=refresh_token", "POST", {"refresh_token": refresh}
            )
            account = await verify_token(tokens.get("access_token", ""))
            set_cookies(response, tokens)
    except SupabaseError as err:
        if err.status_code != 401:
            raise HTTPException(err.status_code, err.detail) from err
        if response is not None:
            clear_cookies(response)
    if require_verified:
        if account is None:
            raise HTTPException(401, "Create an account and sign in to continue.")
        if not account.email_verified:
            raise HTTPException(403, "Confirm your email to use live Muse and save your work.")
    return account


async def snapshot(account: AccountSession | None) -> dict[str, Any]:
    """Return safe identity and durable trial usage without tokens."""
    result: dict[str, Any] = {
        "configured": configured() and get_settings().accounts_required,
        "user": None,
        "usage": None,
        "live_available": False,
    }
    if account is None:
        return result
    result["user"] = {
        "id": account.user_id,
        "email": account.email,
        "email_verified": account.email_verified,
    }
    if account.email_verified:
        usage = await get_supabase_client().rpc("muse_usage_status", {"p_user_id": account.user_id})
        if usage.get("allowed") is not True:
            raise SupabaseError(503, "Usage accounting is unavailable. Try again shortly.")
        result["usage"] = {
            key: usage.get(key) for key in ("plan", "used", "limit", "remaining", "resets_at")
        }
        result["live_available"] = bool(
            usage.get("live_available") and usage.get("remaining", 0) > 0
        )
    return result


def verify_workspace_owner(
    account: AccountSession,
    header_owner: str | None = None,
    body_owner: str | None = None,
    *,
    require_binding: bool = False,
) -> None:
    """Enforce that workspace reads/writes match the tab's expected account owner."""
    normalized_header = header_owner.strip() if isinstance(header_owner, str) else None
    normalized_body = body_owner.strip() if isinstance(body_owner, str) else None
    if require_binding and not normalized_header and not normalized_body:
        raise HTTPException(
            409, "The account changed while saving. Reload your workspace before saving."
        )
    if normalized_header is not None and normalized_header != account.user_id:
        raise HTTPException(
            409, "The account changed in another tab. Reload your workspace before continuing."
        )
    if normalized_body is not None and normalized_body != account.user_id:
        raise HTTPException(
            409, "The account changed while saving. Reload your workspace before saving."
        )


async def load_workspace(account: AccountSession) -> dict[str, Any]:
    """Retrieve only the server-verified creator's saved document."""
    rows = await get_supabase_client().workspace(account.user_id)
    row = rows[0] if rows else {"document": None, "version": 0}
    return {**row, "owner_id": account.user_id}


async def save_workspace(
    account: AccountSession,
    document: dict[str, Any],
    expected_version: int | None,
    expected_owner: str | None = None,
) -> dict[str, Any]:
    """Persist a bounded document with an atomic version and owner comparison."""
    if expected_owner is not None:
        verify_workspace_owner(account, body_owner=expected_owner)
    if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) > 3 * 1024 * 1024:
        raise HTTPException(413, "Save a smaller workspace.")
    result = await get_supabase_client().rpc(
        "muse_save_workspace",
        {
            "p_user_id": account.user_id,
            "p_document": document,
            "p_expected_version": expected_version,
        },
    )
    if result.get("allowed") is not True:
        status = result.get("status_code")
        status = status if status in {403, 409, 413} else 503
        messages = {
            403: "Confirm your email to save your work.",
            409: "Your workspace changed. Reload before saving.",
            413: "Save a smaller workspace.",
        }
        raise HTTPException(status, messages.get(status, "Workspace saving is unavailable."))
    return {"version": result["version"], "document": document, "owner_id": account.user_id}


def _oauth_secret() -> bytes:
    settings = get_settings()
    secret = getattr(settings, "supabase_secret_key", "") or getattr(
        settings, "google_client_secret", ""
    )
    if not secret:
        raise HTTPException(503, "Accounts are not configured on this server.")
    return secret.encode("utf-8")


def sign_oauth_state(next_path: str) -> str:
    """Create a short-lived HMAC-signed state token for OAuth CSRF protection."""
    payload = json.dumps(
        {"next": safe_next_path(next_path), "ts": int(time.time()), "nonce": secrets.token_hex(12)},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(_oauth_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


def verify_oauth_state(state: str | None, cookie_state: str | None) -> str:
    """Verify the OAuth state matches the HttpOnly cookie and HMAC signature."""
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise HTTPException(400, "That Google sign-in request expired. Please try again.")
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(400, "Invalid Google sign-in state.")
    encoded, sig = parts
    expected = hmac.new(_oauth_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Invalid Google sign-in state.")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if abs(int(time.time()) - int(data.get("ts", 0))) > 600:
            raise HTTPException(400, "That Google sign-in request expired. Please try again.")
        return safe_next_path(data.get("next"))
    except (ValueError, TypeError) as err:
        raise HTTPException(400, "Invalid Google sign-in state.") from err


async def start_google_oauth(
    request: Request, response: Response, next_path: str | None = None
) -> str:
    """Build a Google OAuth redirect URL via direct Google OAuth or Supabase Auth."""
    settings = get_settings()
    if not (configured() and getattr(settings, "accounts_required", False)):
        raise HTTPException(503, "Accounts are not configured on this server.")
    target = safe_next_path(next_path)
    base_url = request_base_url(request)
    client_id = getattr(settings, "google_client_id", "").strip()
    client_secret = getattr(settings, "google_client_secret", "").strip()
    if client_id and client_secret:
        state = sign_oauth_state(target)
        response.set_cookie(
            "muse_oauth_state",
            state,
            max_age=600,
            secure=getattr(settings, "account_cookie_secure", True),
            httponly=True,
            samesite="lax",
            path="/",
        )
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": f"{base_url}/api/v1/account/oauth/google/callback",
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    auth_settings = await get_supabase_client().auth("settings")
    external = auth_settings.get("external") if isinstance(auth_settings, dict) else {}
    if isinstance(external, dict) and external.get("google") is True:
        supabase_base = getattr(settings, "supabase_url", "").rstrip("/")
        query = urlencode(
            {
                "provider": "google",
                "redirect_to": f"{base_url}{target}",
                "prompt": "select_account",
            }
        )
        return f"{supabase_base}/auth/v1/authorize?{query}"

    raise HTTPException(
        503,
        "Google sign-in is not enabled on this server yet. Use your email and password below.",
    )


async def complete_google_oauth(
    request: Request, code: str | None, state: str | None, error: str | None
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Complete direct Google OAuth callback and mint a verified Supabase session."""
    if error:
        return "/account", None, "Google sign-in was cancelled or denied. You can sign in below."
    try:
        target = verify_oauth_state(state, request.cookies.get("muse_oauth_state"))
    except HTTPException as exc:
        return "/account", None, str(exc.detail)
    if not code:
        return target, None, "Google sign-in did not return an authorization code."
    settings = get_settings()
    client_id = getattr(settings, "google_client_id", "").strip()
    client_secret = getattr(settings, "google_client_secret", "").strip()
    if not client_id or not client_secret:
        return target, None, "Google sign-in is not configured on this server."
    base_url = request_base_url(request)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as http:
            token_resp = await http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": f"{base_url}/api/v1/account/oauth/google/callback",
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.is_error:
                return target, None, "Could not verify your Google account. Please try again."
            google_access = token_resp.json().get("access_token")
            if not isinstance(google_access, str) or not google_access:
                return target, None, "Could not verify your Google account. Please try again."
            userinfo_resp = await http.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {google_access}", "Accept": "application/json"},
            )
            if userinfo_resp.is_error:
                return target, None, "Could not read your Google profile. Please try again."
            profile = userinfo_resp.json()
    except httpx.HTTPError:
        return target, None, "Google sign-in timed out. Please try again."

    email = str(profile.get("email") or "").strip().lower()
    if not email or not profile.get("email_verified"):
        return target, None, "Your Google account must have a verified email address."

    try:
        link = await get_supabase_client().auth(
            "admin/generate_link",
            "POST",
            {"type": "magiclink", "email": email},
            secret=True,
        )
        hashed_token = link.get("hashed_token")
        if not isinstance(hashed_token, str) or not hashed_token:
            return target, None, "Could not create your Muse session. Please try again."
        tokens = await get_supabase_client().auth(
            "verify",
            "POST",
            {"type": "magiclink", "token_hash": hashed_token},
        )
        await verify_token(tokens.get("access_token", ""))
        return target, tokens, None
    except SupabaseError as err:
        return target, None, err.detail
