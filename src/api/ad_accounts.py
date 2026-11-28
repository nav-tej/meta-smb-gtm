"""Read-only Meta Ads connection and insights routes (Phase 1a).

Mounted under `/api/v1/ad-accounts/meta/*` and active only when `AD_CONNECT_ENABLED=true`.
When `AD_CONNECT_ENABLED=false` (the default), every route in this module returns HTTP 404.
All routes require a signed-in, email-verified Muse seller account.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from src.clients.ad_networks.base import (
    AdNetworkAuthError,
    AdNetworkError,
    AdNetworkIncompleteError,
    AdNetworkPermissionError,
    AdNetworkRateLimitError,
)
from src.clients.ad_networks.meta import MetaAdsReadClient, normalize_meta_account_id
from src.config import get_settings
from src.models.bids import CampaignPerformance
from src.services.accounts import AccountSession, request_base_url, resolve_account
from src.services.ad_connections import (
    AD_OAUTH_STATE_COOKIE,
    AD_OAUTH_STATE_TTL_SECONDS,
    AdConnectionError,
    build_meta_oauth_authorize_url,
    complete_meta_oauth_callback,
    disconnect_meta_connection,
    list_meta_connections,
    load_meta_connection,
    mark_meta_connection_status,
    sign_meta_oauth_state,
)
from src.services.ad_insights import fetch_meta_campaign_performance

logger = logging.getLogger(__name__)


def require_ad_connect_enabled() -> None:
    """Return 404 whenever AD_CONNECT_ENABLED is false so routes behave as unmounted."""
    if not get_settings().ad_connect_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


async def require_verified_seller(request: Request, response: Response) -> AccountSession:
    """Require a signed-in, email-verified Muse seller account."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    return account


router = APIRouter(
    prefix="/ad-accounts/meta",
    tags=["ad-accounts"],
    dependencies=[Depends(require_ad_connect_enabled)],
)


class MetaInsightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=128)
    start_date: date | None = None
    end_date: date | None = None


class MetaDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=128)


def _callback_uri(request: Request) -> str:
    base = request_base_url(request).rstrip("/")
    return f"{base}/api/v1/ad-accounts/meta/callback"


def _set_state_cookie(response: Response, state: str) -> None:
    settings = get_settings()
    response.set_cookie(
        AD_OAUTH_STATE_COOKIE,
        state,
        max_age=AD_OAUTH_STATE_TTL_SECONDS,
        secure=getattr(settings, "account_cookie_secure", True),
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_state_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        AD_OAUTH_STATE_COOKIE,
        path="/",
        secure=getattr(settings, "account_cookie_secure", True),
        httponly=True,
        samesite="lax",
    )


@router.get("/connect")
async def meta_oauth_connect_redirect(
    request: Request,
    next: Annotated[str | None, Query(max_length=64)] = "/#tab-bids",
) -> RedirectResponse:
    """Start read-only Meta OAuth (`ads_read` only) with a user-bound signed state cookie."""
    probe = Response()
    account = await require_verified_seller(request, probe)
    settings = get_settings()
    try:
        state = sign_meta_oauth_state(account.user_id, next_path=next, settings=settings)
        url = build_meta_oauth_authorize_url(
            redirect_uri=_callback_uri(request),
            state=state,
            settings=settings,
        )
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    _set_state_cookie(probe, state)
    redirect = RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    for header, value in probe.raw_headers:
        if header.lower() == b"set-cookie":
            redirect.raw_headers.append((header, value))
    return redirect


ALLOWED_AD_CONNECT_ERROR_CODES = frozenset(
    {
        "cancelled",
        "expired_state",
        "wrong_account",
        "invalid_state",
        "no_ad_accounts",
        "signin_required",
        "connect_failed",
    }
)

_CALLBACK_ERROR_CODE_MAP: dict[str, str] = {
    "oauth_denied": "cancelled",
    "cancelled": "cancelled",
    "expired_oauth_state": "expired_state",
    "expired_state": "expired_state",
    "cross_user_oauth_state": "wrong_account",
    "wrong_account": "wrong_account",
    "invalid_oauth_state": "invalid_state",
    "missing_code": "invalid_state",
    "invalid_state": "invalid_state",
    "no_ad_accounts": "no_ad_accounts",
    "signin_required": "signin_required",
}


def normalize_callback_error_code(raw_code: str | None) -> str:
    """Map internal callback error identifiers to the fixed public allowlist (never free text)."""
    mapped = _CALLBACK_ERROR_CODE_MAP.get((raw_code or "").strip(), "connect_failed")
    return mapped if mapped in ALLOWED_AD_CONNECT_ERROR_CODES else "connect_failed"


def _callback_error_redirect(
    error_code: str,
    *,
    probe: Response | None = None,
) -> RedirectResponse:
    safe_code = normalize_callback_error_code(error_code)
    query = urlencode({"ad_connect_error": safe_code})
    redirect = RedirectResponse(
        f"/?{query}#tab-bids",
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
    if probe is not None:
        for header, value in probe.raw_headers:
            if header.lower() == b"set-cookie":
                redirect.raw_headers.append((header, value))
    _clear_state_cookie(redirect)
    return redirect


@router.post("/connect")
async def meta_oauth_connect_url(
    request: Request,
    response: Response,
    next: Annotated[str | None, Query(max_length=64)] = "/#tab-bids",
) -> dict[str, str]:
    """Return the read-only Meta OAuth authorization URL while setting the signed state cookie."""
    account = await require_verified_seller(request, response)
    settings = get_settings()
    try:
        state = sign_meta_oauth_state(account.user_id, next_path=next, settings=settings)
        url = build_meta_oauth_authorize_url(
            redirect_uri=_callback_uri(request),
            state=state,
            settings=settings,
        )
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    _set_state_cookie(response, state)
    config_id = settings.meta_login_config_id.strip()
    payload: dict[str, str] = {"provider": "meta", "url": url}
    if config_id:
        payload["config_id"] = config_id
    else:
        payload["scope"] = "ads_read"
    return payload


@router.get("/callback")
async def meta_oauth_callback(request: Request) -> RedirectResponse:
    """Verify user-bound state, exchange code for long-lived token, or redirect to #tab-bids."""
    probe = Response()
    try:
        account = await resolve_account(request, probe, require_verified=False)
    except HTTPException:
        account = None
    if account is None or not account.email_verified:
        return _callback_error_redirect("signin_required", probe=probe)

    settings = get_settings()
    try:
        target, saved = await complete_meta_oauth_callback(
            user_id=account.user_id,
            code=request.query_params.get("code"),
            state=request.query_params.get("state"),
            cookie_state=request.cookies.get(AD_OAUTH_STATE_COOKIE),
            error=request.query_params.get("error"),
            redirect_uri=_callback_uri(request),
            settings=settings,
        )
    except AdConnectionError as err:
        return _callback_error_redirect(err.code, probe=probe)

    dest_path, _, dest_hash = target.partition("#")
    base_path = dest_path or "/"
    query = urlencode(
        {
            "ad_connect": "meta",
            "accounts": str(len(saved)),
        }
    )
    final_url = f"{base_path}?{query}" + (f"#{dest_hash}" if dest_hash else "#tab-bids")
    redirect = RedirectResponse(final_url, status_code=302, headers={"Cache-Control": "no-store"})
    for header, value in probe.raw_headers:
        if header.lower() == b"set-cookie":
            redirect.raw_headers.append((header, value))
    _clear_state_cookie(redirect)
    return redirect


@router.get("/accounts")
async def list_connected_meta_accounts(
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """List the signed-in seller's connected Meta ad accounts (no tokens or ciphertexts)."""
    account = await require_verified_seller(request, response)
    try:
        connections = await list_meta_connections(account.user_id)
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
    return {
        "enabled": True,
        "network": "meta",
        "accounts": [c.model_dump() for c in connections],
    }


def _resolve_date_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    resolved_end = end_date or today
    resolved_start = start_date or (resolved_end - timedelta(days=13))
    if resolved_end < resolved_start:
        logger.warning("Ad insights request has reversed date range")
        raise HTTPException(
            status_code=422,
            detail=(
                "The end date is before the start date. "
                "Choose an end date on or after the start date."
            ),
        )
    if (resolved_end - resolved_start).days > 90:
        raise HTTPException(
            status_code=422,
            detail="Choose a date range of 90 days or fewer.",
        )
    return resolved_start, resolved_end


async def _fetch_connected_insights(
    account: AccountSession,
    account_id: str,
    start_date: date | None,
    end_date: date | None,
) -> CampaignPerformance | JSONResponse:
    resolved_start, resolved_end = _resolve_date_range(start_date, end_date)
    settings = get_settings()
    try:
        summary, token = await load_meta_connection(
            account.user_id,
            account_id,
            settings=settings,
        )
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err

    read_client = MetaAdsReadClient(access_token=token, settings=settings)
    try:
        performance = await fetch_meta_campaign_performance(
            summary.external_account_id,
            start_date=resolved_start,
            end_date=resolved_end,
            account_name=summary.account_name or "Meta Ad Account",
            currency=summary.currency,
            client=read_client,
        )
    except AdNetworkAuthError:
        with contextlib.suppress(AdConnectionError):
            await mark_meta_connection_status(
                account.user_id,
                summary.external_account_id,
                status="expired",
            )
        return JSONResponse(
            status_code=401,
            content={
                "detail": (
                    "Your Meta Ads connection expired. Reconnect to load your latest results."
                ),
                "code": "meta_token_expired",
                "reconnect_required": True,
                "account_id": summary.external_account_id,
            },
            headers={"Cache-Control": "no-store"},
        )
    except AdNetworkRateLimitError as err:
        raise HTTPException(
            status_code=429,
            detail="Meta asked Muse to slow down. Try again in a minute.",
        ) from err
    except AdNetworkPermissionError as err:
        raise HTTPException(
            status_code=403,
            detail=(
                "Meta did not give Muse access to this ad account's results. "
                "Reconnect and allow access."
            ),
        ) from err
    except AdNetworkIncompleteError as err:
        # Partial history would skew the bid advice, so nothing is returned.
        raise HTTPException(
            status_code=422,
            detail=(
                "This ad account has more results than Muse can load at once. "
                "Try a shorter date range."
            ),
        ) from err
    except AdNetworkError as err:
        raise HTTPException(
            status_code=502,
            detail="Could not load your ad results from Meta right now. Please try again.",
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=422,
            detail="No daily ad results were found for this ad account in the selected dates.",
        ) from err
    finally:
        await read_client.aclose()

    with contextlib.suppress(AdConnectionError):
        await mark_meta_connection_status(
            account.user_id,
            summary.external_account_id,
            status="active",
        )
    return performance


@router.get("/insights", response_model=CampaignPerformance)
async def get_connected_meta_insights(
    request: Request,
    response: Response,
    account_id: Annotated[str, Query(min_length=1, max_length=128)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> CampaignPerformance | JSONResponse:
    """Fetch daily Meta insights for a connected ad account and map into `CampaignPerformance`."""
    account = await require_verified_seller(request, response)
    return await _fetch_connected_insights(account, account_id, start_date, end_date)


@router.post("/insights", response_model=CampaignPerformance)
async def post_connected_meta_insights(
    body: MetaInsightsRequest,
    request: Request,
    response: Response,
) -> CampaignPerformance | JSONResponse:
    """Fetch daily Meta insights (POST variant) and return `CampaignPerformance` for Bid Advisor."""
    account = await require_verified_seller(request, response)
    return await _fetch_connected_insights(
        account,
        body.account_id,
        body.start_date,
        body.end_date,
    )


@router.post("/disconnect")
async def disconnect_connected_meta_account(
    request: Request,
    response: Response,
    body: MetaDisconnectRequest | None = None,
    account_id: Annotated[str | None, Query(max_length=128)] = None,
) -> dict[str, Any]:
    """Disconnect a seller's Meta ad account and delete its stored token ciphertext."""
    account = await require_verified_seller(request, response)
    target_account_id = (body.account_id if body is not None else account_id) or ""
    if not target_account_id.strip():
        logger.warning("Ad disconnect requested without account selection")
        raise HTTPException(
            status_code=422, detail="Choose the Meta ad account you want to disconnect."
        )
    try:
        normalized_id = normalize_meta_account_id(target_account_id)
        await disconnect_meta_connection(account.user_id, normalized_id)
    except ValueError as err:
        raise HTTPException(status_code=422, detail="Enter a valid Meta ad account ID.") from err
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
    return {"disconnected": True, "account_id": normalized_id}


@router.delete("/disconnect")
async def delete_connected_meta_account(
    request: Request,
    response: Response,
    account_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> dict[str, Any]:
    """DELETE alias to disconnect a seller's Meta ad account and remove its ciphertext."""
    account = await require_verified_seller(request, response)
    try:
        normalized_id = normalize_meta_account_id(account_id)
        await disconnect_meta_connection(account.user_id, normalized_id)
    except ValueError as err:
        raise HTTPException(status_code=422, detail="Enter a valid Meta ad account ID.") from err
    except AdConnectionError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
    return {"disconnected": True, "account_id": normalized_id}
