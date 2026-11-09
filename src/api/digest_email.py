"""Weekly competitor digest by email: sign-up, confirm, unsubscribe and the weekly cron."""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.api.demo import _client_ip_hash
from src.config import get_settings
from src.services import alerts, digest_email, durable_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digest", tags=["digest"])
SENT = "If that address can receive email, a confirmation link is on its way. Check your inbox."


class SubscribeRequest(BaseModel):
    email: str = Field(min_length=6, max_length=254)
    competitors: list[str] = Field(min_length=1, max_length=3)


@router.get("/subscription")
async def subscription_status() -> dict[str, bool]:
    """Whether the sign-up form should be offered."""
    return {"available": digest_email.available()}


@router.post("/subscribe")
async def subscribe(body: SubscribeRequest, request: Request) -> dict[str, str]:
    try:
        await digest_email.subscribe(body.email, body.competitors, _client_ip_hash(request))
    except digest_email.DigestError as err:
        raise HTTPException(err.status_code, err.detail) from err
    return {"message": SENT}


@router.get("/confirm", include_in_schema=False)
async def confirm(
    id: Annotated[str, Query(max_length=64)] = "",
    c: Annotated[str, Query(max_length=2000)] = "",
    t: Annotated[str, Query(max_length=64)] = "",
) -> RedirectResponse:
    try:
        ok = await digest_email.confirm(id, c, t)
    except digest_email.DigestError:
        ok = False
    return RedirectResponse(f"/digest?email={'confirmed' if ok else 'link-invalid'}", 303)


@router.get("/unsubscribe", include_in_schema=False)
async def unsubscribe_link(
    id: Annotated[str, Query(max_length=64)] = "",
    t: Annotated[str, Query(max_length=64)] = "",
) -> RedirectResponse:
    try:
        ok = await digest_email.unsubscribe(id, t)
    except digest_email.DigestError:
        ok = False
    return RedirectResponse(f"/digest?email={'unsubscribed' if ok else 'link-invalid'}", 303)


@router.post("/unsubscribe", include_in_schema=False)
async def unsubscribe_one_click(
    id: Annotated[str, Query(max_length=64)] = "",
    t: Annotated[str, Query(max_length=64)] = "",
) -> JSONResponse:
    """RFC 8058 one-click unsubscribe from the mail client."""
    try:
        ok = await digest_email.unsubscribe(id, t)
    except digest_email.DigestError as err:
        raise HTTPException(err.status_code, err.detail) from err
    if not ok:
        raise HTTPException(400, "This link is no longer valid.")
    return JSONResponse({"unsubscribed": True})


@router.get("/send", include_in_schema=False)
async def weekly_send(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    """Weekly Vercel Cron entry point. Repeating it sends nothing new (6-day rule in SQL)."""
    secret = get_settings().cron_secret
    if secret:
        if not (authorization and hmac.compare_digest(authorization, f"Bearer {secret}")):
            raise HTTPException(401, "This scheduled job needs the cron secret.")
    elif not request.headers.get("user-agent", "").startswith("vercel-cron"):
        raise HTTPException(403, "Scheduled job only.")
    await durable_state.hydrate_monitor()
    try:
        summary = await digest_email.run_weekly()
    except digest_email.DigestError as err:
        logger.error("DIGEST_SEND_FAILED %s", err.detail)
        await alerts.alert("Weekly digest not sent", err.detail)
        raise HTTPException(err.status_code, err.detail) from err
    logger.info("Weekly digest: %s", summary)
    if summary["failed"]:
        await alerts.alert("Weekly digest partly failed", f"Summary: {summary}")
    return summary
