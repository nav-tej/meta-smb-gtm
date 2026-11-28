"""Durable pre-call usage reservations shared across server instances.

Each HTTP operation gets one context after the auth layer verifies the account. Every actual
Meta request, including a JSON-repair attempt, reserves separately. Reservations are retained
on failure because an interrupted or timed-out upstream request can still be billed.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from src.config import get_settings

logger = logging.getLogger(__name__)
RUNS_UNAVAILABLE = "Muse couldn't check your remaining runs. Try again in a minute."
LIVE_REQUEST_INVALID = "Muse couldn't start that live request. Try again, or use a saved result."
RUN_FINISH_FAILED = "Muse couldn't finish recording this run. Try again in a minute."
# Reviewed server copy only; never return arbitrary database response text.
_PUBLIC_RUN_MESSAGES = frozenset(
    {
        "Live Muse is paused. Saved drafts still work.",
        "This request already started. Check its result.",
        "Your 3 free Muse runs are used. Pick a plan for more runs.",
        "Your plan runs are used. Upgrade or wait for renewal.",
        "Too many requests from this network. Try later.",
        "Your earlier Muse request is still running.",
        "Confirm your email to use live Muse.",
        "Create an account and sign in to use live Muse.",
    }
)


class UsageLimitError(Exception):
    """A quota, account, or accounting-store failure blocks a live operation."""

    def __init__(self, status_code: int, detail: str, *, retry_after: int | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


@dataclass(frozen=True)
class UsageContext:
    operation_id: str
    user_id: str


_request_context: ContextVar[UsageContext | None] = ContextVar("muse_usage_context", default=None)
_MODEL_KINDS = {
    "muse-spark-1.3": frozenset({"spark", "text", "chat"}),
    "muse-image-1.0": frozenset({"image"}),
    "sam-3.1": frozenset({"sam", "segmentation"}),
    "muse-voice-transcribe-1.0": frozenset({"voice", "transcription"}),
}


def clear_request_context() -> None:
    """Clear identity after every request, including rejected requests and cleanup failures."""
    _request_context.set(None)


def current_operation_id() -> str | None:
    """Return the opaque current operation ID, never an auth token or network identity."""
    context = _request_context.get()
    return context.operation_id if context else None


def current_user_id() -> str | None:
    """The server-verified account behind the current live run, if any."""
    context = _request_context.get()
    return context.user_id if context else None


async def _rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
    # Lazy import keeps this service independent of auth-route initialization.
    try:
        from src.clients.supabase import get_supabase_client

        result = await get_supabase_client().rpc(name, params)
    except Exception as err:
        logger.warning("Run accounting request failed (%s)", type(err).__name__)
        raise UsageLimitError(503, RUNS_UNAVAILABLE) from err
    if isinstance(result, list) and len(result) == 1:
        result = result[0]
    if not isinstance(result, dict) or result.get("allowed") is not True:
        if isinstance(result, dict) and result.get("allowed") is False:
            status = result.get("status_code")
            if status not in {400, 401, 403, 404, 409, 413, 429, 503}:
                status = 503
            message = result.get("message")
            messages = {
                "global_attempt_limit": (
                    "Live Muse is busy right now. View saved results or try again later."
                ),
                "account_attempt_limit": (
                    "You have started many live requests this hour. Try again later."
                ),
                "invalid_operation": LIVE_REQUEST_INVALID,
                "invalid_provider_reservation": LIVE_REQUEST_INVALID,
                "invalid_status": RUN_FINISH_FAILED,
                "inactive_operation": "That live request is no longer active. Start it again.",
                "provider_call_already_reserved": "This request already started. Check its result.",
                "operation_call_limit": (
                    "This run reached its request limit. Try a smaller request."
                ),
                "operation_not_found": (
                    "Muse couldn't find that run. Reload and check your saved results."
                ),
            }
            detail = (
                message
                if isinstance(message, str) and message in _PUBLIC_RUN_MESSAGES
                else messages.get(str(result.get("code") or ""), RUNS_UNAVAILABLE)
            )
            logger.warning("Run accounting refused request (HTTP %s)", status)
            retry = result.get("retry_after")
            raise UsageLimitError(
                status,
                detail,
                retry_after=retry if type(retry) is int and 1 <= retry <= 3600 else None,
            )
        logger.warning("Run accounting returned an invalid response")
        raise UsageLimitError(503, RUNS_UNAVAILABLE)
    return result


async def authorize_operation(
    user_id: str,
    ip_hash: str,
    request_id: str,
    session_id: str | None = None,
) -> str:
    """Reserve a daily operation for an already server-verified Supabase user."""
    clear_request_context()
    if not getattr(get_settings(), "accounts_required", False):
        return ""
    result = await _rpc(
        "muse_begin_operation",
        {
            "p_user_id": user_id,
            "p_ip_hash": ip_hash,
            "p_request_id": request_id,
            "p_session_id": session_id,
        },
    )
    try:
        operation_id = str(UUID(str(result["operation_id"])))
    except (KeyError, ValueError, TypeError, AttributeError) as err:
        logger.warning("Run identity response invalid (%s)", type(err).__name__)
        raise UsageLimitError(503, RUNS_UNAVAILABLE) from err
    _request_context.set(UsageContext(operation_id=operation_id, user_id=user_id))
    return operation_id


async def reserve_provider(kind: str, model: str, amount_micros: int) -> dict[str, Any] | None:
    """Charge a conservative reservation before an upstream attempt; never auto-refund it."""
    context = _request_context.get()
    if context is None:
        if getattr(get_settings(), "accounts_required", False):
            raise UsageLimitError(401, "Create an account and sign in to use live Muse.")
        return None
    if (
        isinstance(amount_micros, bool)
        or not isinstance(amount_micros, int)
        or not 0 < amount_micros <= 20_000_000
        or kind not in _MODEL_KINDS.get(model, ())
    ):
        logger.warning("Live request reservation failed model/amount validation")
        raise UsageLimitError(400, LIVE_REQUEST_INVALID)
    return await _rpc(
        "muse_reserve_provider",
        {
            "p_operation_id": context.operation_id,
            "p_kind": kind,
            "p_amount_micros": amount_micros,
            "p_model": model,
            "p_call_id": str(uuid4()),
        },
    )


async def finish_operation(status: str = "completed", *, operation_id: str | None = None) -> None:
    """Finish the current operation without refunding any provider reservation."""
    context = _request_context.get()
    target = operation_id or (context.operation_id if context else None)
    try:
        if target is not None:
            if status not in {"completed", "failed", "refunded"}:
                logger.warning("Run completion status invalid")
                raise UsageLimitError(400, RUN_FINISH_FAILED)
            await _rpc(
                "muse_finish_operation",
                {"p_operation_id": target, "p_status": status},
            )
    finally:
        clear_request_context()


async def reserve_public_work(
    kind: str, ip_hash: str, count: int, address_hash: str | None = None
) -> None:
    """Reserve free public work durably before crawling or sending an Auth email."""
    try:
        await _rpc(
            "muse_reserve_public_work",
            {
                "p_kind": kind,
                "p_ip_hash": ip_hash,
                "p_count": count,
                "p_address_hash": address_hash,
            },
        )
    except UsageLimitError as err:
        if err.status_code == 429:
            retry = err.retry_after or (600 if kind == "scan" else 900)
            detail = (
                "Muse has received many website checks. "
                "Try again later, or enter the details yourself."
                if kind == "scan"
                else "Too many email requests. Wait a few minutes, then check your inbox."
            )
            raise HTTPException(429, detail, headers={"Retry-After": str(retry)}) from err
        raise HTTPException(
            503, "Muse can't start this request right now. Please try again shortly."
        ) from err
