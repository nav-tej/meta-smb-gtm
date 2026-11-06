"""Spending guard for public deployments.

With DEMO_MODE on, routes that call Muse serve saved live results instead. A real call needs
`?live=true` plus either a verified account with runs remaining (ACCOUNTS_REQUIRED) or an
`X-Demo-Key` header matching DEMO_KEY (legacy presenter path), and is capped at
LIVE_CALLS_PER_HOUR. The cap is held in memory, so on serverless hosts it applies per running
instance (cold starts reset it); it bounds abuse rather than enforcing an exact global quota.

Every non-account live request also spends one server-side credit (src/services/credits.py),
reserved before the route runs. It is refunded if the request made no billable Muse call (a
cache hit), failed, or was answered by a cached/demo fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query, Request, Response, status

from src.clients.meta import track_provider_calls
from src.config import get_settings
from src.services import credits, live_quota

logger = logging.getLogger(__name__)

WINDOW_SECONDS = live_quota.WINDOW_SECONDS
# Same deque object as live_quota's, kept here for existing callers and tests.
_live_calls: deque[float] = live_quota._live_calls
_reserve_live_slot = live_quota.reserve


def _client_ip_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(ip.encode()).hexdigest()


def valid_demo_key(x_demo_key: str | None) -> bool:
    key = get_settings().demo_key
    return bool(key and x_demo_key and hmac.compare_digest(x_demo_key.encode(), key.encode()))


def set_credit_cookie(response: Response, holder: credits.Holder) -> None:
    if holder.new_cookie:
        response.set_cookie(
            credits.COOKIE_NAME,
            holder.new_cookie,
            max_age=credits.COOKIE_MAX_AGE,
            secure=get_settings().account_cookie_secure,
            httponly=True,
            samesite="lax",
        )


def credit_holder(request: Request, response: Response, *, presenter: bool) -> credits.Holder:
    holder = credits.holder_for(request.cookies.get(credits.COOKIE_NAME), presenter=presenter)
    set_credit_cookie(response, holder)
    return holder


async def _spend_credit(
    request: Request, response: Response, *, presenter: bool
) -> AsyncIterator[bool]:
    """Reserve one credit, run the route, then keep or refund it based on what happened."""
    log = track_provider_calls()
    if not get_settings().credits_enabled:
        yield True
        return
    holder = credit_holder(request, response, presenter=presenter)
    try:
        hold = credits.reserve(holder.id, label=request.url.path)
    except credits.CreditsExhaustedError:
        live_quota.release_reserved()
        raise
    response.headers["X-Muse-Credits"] = str(max(0, credits.balance(holder.id)))
    try:
        yield True
    except BaseException:
        credits.refund(hold, "request failed")
        raise
    if log["hits"] and not log["calls"]:
        # Answered from the cache: no billable call happened.
        credits.refund(hold, "cache hit")
        live_quota.release_reserved()
    elif log["fallbacks"]:
        credits.refund(hold, "served a fallback")
    else:
        credits.commit(hold)


async def live_mode(
    request: Request,
    response: Response,
    live: Annotated[bool, Query(description="Make a real (billed) Muse call.")] = False,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> AsyncIterator[bool]:
    """Yield True when this request may call Muse; False means saved demo result.

    With accounts enabled, one run is authorized per live request and finished when
    the route completes, so 1 run = 1 live action against the user's quota.
    """
    from src.services import usage_meter
    from src.services.accounts import resolve_account

    settings = get_settings()
    if (
        not settings.accounts_required
        and not settings.demo_mode
        and not settings.hosted_environment
    ):
        # Local full version: no key needed, but live calls still spend server credits.
        async for allowed in _spend_credit(request, response, presenter=valid_demo_key(x_demo_key)):
            yield allowed
        return
    if not live:
        yield False
        return
    if settings.accounts_required:
        account = await resolve_account(request, require_verified=True)
        assert account is not None
        operation_id = await usage_meter.authorize_operation(
            account.user_id, _client_ip_hash(request), str(uuid4()), account.session_id
        )
        logger.warning(
            "LIVE Muse run authorized: %s user=%s op=%s",
            request.url.path,
            account.user_id,
            operation_id,
        )
        try:
            yield True
        finally:
            await usage_meter.finish_operation("completed", operation_id=operation_id)
        return
    if not valid_demo_key(x_demo_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Live calls need a valid X-Demo-Key.")
    remaining = _reserve_live_slot(settings.live_calls_per_hour)
    logger.warning(
        "LIVE Muse call allowed: %s at %s (%d left this hour)",
        request.url.path,
        datetime.now(UTC).isoformat(),
        remaining,
    )
    async for allowed in _spend_credit(request, response, presenter=True):
        yield allowed


LiveMode = Annotated[bool, Depends(live_mode)]


def demo_unavailable(feature: str) -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=(
            f"{feature} has no saved demo result. This deployment is in demo mode; "
            "add ?live=true with a valid X-Demo-Key header to run it live."
        ),
    )
