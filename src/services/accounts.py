"""Verified account sessions and creator-owned workspace persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, Response

from src.clients.supabase import SupabaseError, configured, get_supabase_client
from src.config import get_settings

SAFE_NEXT_PATHS = {"/", "/account", "/today", "/create", "/digest", "/portal", "/welcome"}
logger = logging.getLogger(__name__)

# Signup, resend and reset all reach Supabase from this server's IP, so Supabase's own
# per-IP limits behave like one shared bucket. This per-instance limiter stops one client
# from draining that bucket; it is best effort on serverless (each instance counts alone).
EMAIL_SEND_WINDOW_SECONDS = 15 * 60
EMAIL_SENDS_PER_IP = 8
EMAIL_SENDS_PER_ADDRESS = 3
_email_sends: dict[str, deque[float]] = {}


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
        logger.warning("Account request refused (expected JSON)")
        raise HTTPException(
            415, "Muse couldn't read your account request. Reload the page and try again."
        )


def _hashed(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def throttle_email_send(request: Request, email: str, now: float | None = None) -> None:
    """Refuse a confirmation/reset email when this network or address asked too often."""
    now = time.monotonic() if now is None else now
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "")
    buckets = (
        ("ip:" + _hashed(ip), EMAIL_SENDS_PER_IP),
        ("email:" + _hashed(email.strip().lower()), EMAIL_SENDS_PER_ADDRESS),
    )
    cutoff = now - EMAIL_SEND_WINDOW_SECONDS
    for key in [key for key, times in _email_sends.items() if not times or times[-1] < cutoff]:
        del _email_sends[key]
    for key, limit in buckets:
        times = _email_sends.get(key, deque())
        while times and times[0] < cutoff:
            times.popleft()
        if len(times) >= limit:
            raise HTTPException(
                429, "Too many email requests. Wait a few minutes, then check your inbox."
            )
    for key, _ in buckets:
        _email_sends.setdefault(key, deque()).append(now)


def reset_email_throttle() -> None:
    """Forget recorded sends (tests and process restarts)."""
    _email_sends.clear()


# Signup binding. Supabase keeps the FIRST password when an unconfirmed address is signed up
# again, so whoever registered an address first could sign in once its owner clicks the
# confirmation link. Each signup therefore stores the new password with a hash of a random
# nonce (admin-only app_metadata) and gives that nonce to the signing-up browser. The password
# survives confirmation only when the emailed link lands in the browser holding the latest
# nonce; anywhere else it is replaced and the owner sets a new one (see settle_signup_binding).
SIGNUP_COOKIE = "muse_signup"
SIGNUP_COOKIE_PATH = "/api/v1/account"
SIGNUP_COOKIE_SECONDS = 2 * 86400
SIGNUP_BINDING_KEY = "muse_signup_binding"


async def bind_signup(response: Response, reply: dict[str, Any], email: str, password: str) -> None:
    """Tie the password just chosen at signup to this browser (see SIGNUP_BINDING_KEY)."""
    try:
        user_id = str(UUID(str(reply.get("id"))))
    except ValueError:
        return
    client = get_supabase_client()
    try:
        user = await client.auth(f"admin/users/{user_id}", "GET", secret=True)
    except SupabaseError as err:
        if err.status_code == 404:  # Supabase answers a confirmed address with a random id.
            return
        raise
    if user.get("email_confirmed_at") or str(user.get("email", "")).lower() != email.lower():
        return
    nonce = secrets.token_urlsafe(32)
    await client.auth(
        f"admin/users/{user_id}",
        "PUT",
        {"password": password, "app_metadata": {SIGNUP_BINDING_KEY: _hashed(nonce)}},
        secret=True,
    )
    response.set_cookie(
        SIGNUP_COOKIE,
        nonce,
        max_age=SIGNUP_COOKIE_SECONDS,
        secure=getattr(get_settings(), "account_cookie_secure", True),
        httponly=True,
        samesite="lax",
        path=SIGNUP_COOKIE_PATH,
    )


async def settle_signup_binding(
    request: Request, response: Response, access_token: str, *, from_link: bool
) -> bool:
    """Resolve a pending signup binding for a confirmed account. True if the password was reset.

    Only the confirmation-link landing (from_link=True) in the browser holding the latest nonce
    keeps the signup password. Anywhere else the password is replaced: a landing elsewhere keeps
    its own session and revokes the others; a password sign-in while the binding is pending
    means the account was confirmed without a landing (mail scanner, failed landing, or a race),
    so that password is unproven and every session is revoked.
    """
    client = get_supabase_client()
    user = await client.auth("user", access_token=access_token)
    pending = (user.get("app_metadata") or {}).get(SIGNUP_BINDING_KEY)
    if not pending or not user.get("email_confirmed_at"):
        return False
    try:
        user_id = str(UUID(str(user.get("id"))))
    except ValueError as err:
        logger.warning("Signup binding identity invalid (%s)", type(err).__name__)
        raise SupabaseError(503, "Muse couldn't complete sign-in. Try signing in again.") from err
    nonce = request.cookies.get(SIGNUP_COOKIE, "")
    matches = from_link and bool(nonce) and hmac.compare_digest(_hashed(nonce), str(pending))
    update: dict[str, Any] = {"app_metadata": {SIGNUP_BINDING_KEY: None}}
    if not matches:
        update["password"] = secrets.token_urlsafe(48)
    await client.auth(f"admin/users/{user_id}", "PUT", update, secret=True)
    response.delete_cookie(SIGNUP_COOKIE, path=SIGNUP_COOKIE_PATH)
    if matches:
        return False
    scope = "others" if from_link else "global"
    await client.auth(f"logout?scope={scope}", "POST", access_token=access_token)
    logger.info("Replaced a signup password that was not confirmed in the signup browser")
    return True


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
        logger.warning("Account session response failed token validation")
        raise SupabaseError(503, "Muse couldn't complete sign-in. Try signing in again.")
    if not access or not refresh or len(access) > 12000 or len(refresh) > 12000:
        logger.warning("Account session response failed token validation")
        raise SupabaseError(503, "Muse couldn't complete sign-in. Try signing in again.")
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
    # Only the Auth server sets email_confirmed_at. user_metadata is writable by the user,
    # so a self-declared "email_verified" there proves nothing.
    verified = bool(user.get("email_confirmed_at"))
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
            logger.warning("Account run status request refused")
            raise SupabaseError(
                503, "Muse couldn't check your remaining runs. Try again in a minute."
            )
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
        logger.warning("Account sign-in unavailable (missing configuration)")
        raise HTTPException(503, "Sign-in is unavailable right now. Please try again later.")
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
        logger.warning("Google sign-in state verification failed")
        raise HTTPException(
            400, "Muse couldn't confirm that Google sign-in request. Start sign-in again."
        )
    encoded, sig = parts
    expected = hmac.new(_oauth_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("Google sign-in state verification failed")
        raise HTTPException(
            400, "Muse couldn't confirm that Google sign-in request. Start sign-in again."
        )
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if abs(int(time.time()) - int(data.get("ts", 0))) > 600:
            raise HTTPException(400, "That Google sign-in request expired. Please try again.")
        return safe_next_path(data.get("next"))
    except (ValueError, TypeError) as err:
        logger.warning("Google sign-in state verification failed")
        raise HTTPException(
            400, "Muse couldn't confirm that Google sign-in request. Start sign-in again."
        ) from err


async def start_google_oauth(
    request: Request, response: Response, next_path: str | None = None
) -> str:
    """Build a Google OAuth redirect URL via direct Google OAuth or Supabase Auth."""
    settings = get_settings()
    if not (configured() and getattr(settings, "accounts_required", False)):
        logger.warning("Account sign-in unavailable (missing configuration)")
        raise HTTPException(503, "Sign-in is unavailable right now. Please try again later.")
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


async def _revoke_unproven_password(link: dict[str, Any]) -> None:
    """Close the pre-registration hijack before Google sign-in confirms an existing account.

    Someone can sign up with another person's address and never confirm it. If that person
    later signs in with Google, verifying the link would confirm the account and the
    squatter's password would start working. Replace that unproven password first; if the
    replacement fails, the error stops sign-in before the email is confirmed. An account that
    is confirmed but still has a pending signup binding (see bind_signup) is treated the same.
    """
    confirmed = link.get("email_confirmed_at") or link.get("confirmed_at")
    pending = (link.get("app_metadata") or {}).get(SIGNUP_BINDING_KEY)
    if confirmed and not pending:
        return
    try:
        user_id = str(UUID(str(link.get("id"))))
    except ValueError:
        return
    update: dict[str, Any] = {"password": secrets.token_urlsafe(48)}
    if pending:
        update["app_metadata"] = {SIGNUP_BINDING_KEY: None}
    await get_supabase_client().auth(f"admin/users/{user_id}", "PUT", update, secret=True)
    logger.info("Replaced an unproven account password during Google sign-in")


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
        await _revoke_unproven_password(link)
        tokens = await get_supabase_client().auth(
            "verify",
            "POST",
            {"type": "magiclink", "token_hash": hashed_token},
        )
        await verify_token(tokens.get("access_token", ""))
        return target, tokens, None
    except SupabaseError as err:
        return target, None, err.detail
