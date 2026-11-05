"""Verified account sessions and creator-owned workspace persistence."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException, Request, Response

from src.clients.supabase import SupabaseError, configured, get_supabase_client
from src.config import get_settings


@dataclass(frozen=True)
class AccountSession:
    user_id: str
    email: str
    email_verified: bool
    access_token: str
    session_id: str | None


def trusted_mutation(request: Request) -> None:
    """Reject cross-site cookie mutations, including login and callback injection."""
    settings = get_settings()
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    app = urlsplit(getattr(settings, "app_url", "https://meta-smb-gtm.vercel.app"))
    valid = bool(origin) and origin == f"{app.scheme}://{app.netloc}"
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
    return AccountSession(
        user_id, email, bool(user.get("email_confirmed_at")), access_token, session_id
    )


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


async def load_workspace(account: AccountSession) -> dict[str, Any]:
    """Retrieve only the server-verified creator's saved document."""
    rows = await get_supabase_client().workspace(account.user_id)
    return rows[0] if rows else {"document": None, "version": 0}


async def save_workspace(
    account: AccountSession, document: dict[str, Any], expected_version: int | None
) -> dict[str, Any]:
    """Persist a bounded document with an atomic version comparison."""
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
    return {"version": result["version"], "document": document}
