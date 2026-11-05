"""Durable pre-call usage reservations shared across server instances.

Each HTTP operation gets one context after the auth layer verifies the account. Every actual
Meta request, including a JSON-repair attempt, reserves separately. Reservations are retained
on failure because an interrupted or timed-out upstream request can still be billed.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from src.config import get_settings


class UsageLimitError(Exception):
    """A quota, account, or accounting-store failure blocks a live operation."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
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


async def _rpc(name: str, params: dict[str, Any]) -> dict[str, Any]:
    # Lazy import keeps this service independent of auth-route initialization.
    try:
        from src.clients.supabase import get_supabase_client

        result = await get_supabase_client().rpc(name, params)
    except Exception as err:
        raise UsageLimitError(503, "Usage accounting is unavailable. Try again later.") from err
    if isinstance(result, list) and len(result) == 1:
        result = result[0]
    if not isinstance(result, dict) or result.get("allowed") is not True:
        if isinstance(result, dict) and result.get("allowed") is False:
            status = result.get("status_code")
            if status not in {400, 401, 403, 404, 409, 413, 429, 503}:
                status = 503
            message = result.get("message")
            detail = message[:240] if isinstance(message, str) else "Muse is unavailable right now."
            raise UsageLimitError(status, detail)
        raise UsageLimitError(503, "Usage accounting returned an invalid response.")
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
        raise UsageLimitError(503, "Usage accounting returned an invalid operation.") from err
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
        raise UsageLimitError(400, "Unsupported model or reservation.")
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
            if status not in {"completed", "failed"}:
                raise UsageLimitError(400, "Invalid completion status.")
            await _rpc(
                "muse_finish_operation",
                {"p_operation_id": target, "p_status": status},
            )
    finally:
        clear_request_context()
