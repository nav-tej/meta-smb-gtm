"""Weekly competitor digest by email: sign-up, confirm, unsubscribe and the weekly cron."""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.api.demo import _client_ip_hash
from src.config import get_settings
from src.services import alerts, digest_email, digest_preview, durable_state
from src.services.accounts import resolve_account, verify_workspace_owner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digest", tags=["digest"])
SENT = "If that address can receive email, a confirmation link is on its way. Check your inbox."


class SubscribeRequest(BaseModel):
    competitors: list[str] = Field(min_length=1, max_length=3)
    frequency: str = "weekly"
    topics: list[str] = Field(default_factory=list)
    email: str | None = None


@router.get("/subscription")
async def subscription_status() -> dict[str, bool]:
    """Whether the sign-up form should be offered."""
    return {"available": digest_email.available()}


@router.post("/subscribe")
async def subscribe(body: SubscribeRequest, request: Request, response: Response) -> dict[str, str]:
    """Subscribe to weekly competitor digest (Revision 4: verified account required)."""
    if not digest_email.available():
        raise HTTPException(503, "Email digests open soon.")
    account = await resolve_account(request, response, require_verified=True)
    if not account or not account.email_verified:
        raise HTTPException(
            401, "Sign in with a confirmed email address to subscribe to the competitor digest."
        )
    subscriber_email = account.email
    try:
        await digest_email.subscribe(subscriber_email, body.competitors, _client_ip_hash(request))
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
            logger.warning("Scheduled email delivery refused (authorization)")
            raise HTTPException(
                401, "This email delivery needs authorization. Return to your digest settings."
            )
    elif not request.headers.get("user-agent", "").startswith("vercel-cron"):
        logger.warning("Scheduled email delivery refused (caller)")
        raise HTTPException(
            403, "This address is for scheduled email delivery. Return to your digest settings."
        )
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


# ---------- Batch 2A: Personal digest preview & workspace draft preferences ----------


class DigestDraftPreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cadence: digest_preview.CadenceType = "weekly"
    topics: list[str] = Field(default_factory=lambda: list(digest_preview.CANONICAL_TOPICS))
    timezone: str = digest_preview.DEFAULT_TIMEZONE
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: str | None = Field(default=None, max_length=10)
    competitors: list[str] = Field(default_factory=list, max_length=3)
    expected_version: int | None = Field(default=None, ge=0, strict=True)
    expected_owner: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        return digest_preview.validate_timezone(value)


class DigestPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cadence: digest_preview.CadenceType | None = None
    topics: list[str] | None = None
    timezone: str | None = None
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: str | None = Field(default=None, max_length=10)
    competitors: list[str] | None = Field(default=None, max_length=3)
    expected_owner: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("timezone")
    @classmethod
    def _valid_opt_tz(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return digest_preview.validate_timezone(value)


@router.get("/preferences")
async def get_digest_preferences(
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return signed-in seller's workspace-saved draft digest preferences (never triggers sends)."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        raise HTTPException(401, "Sign in to load your personal digest preferences.")
    verify_workspace_owner(account, x_muse_owner)
    return await digest_preview.load_digest_draft(account)


@router.put("/preferences")
async def save_digest_preferences(
    body: DigestDraftPreferencesBody,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Save draft digest preferences to the signed-in seller's workspace with concurrency check."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        raise HTTPException(401, "Sign in to save your personal digest preferences.")
    verify_workspace_owner(account, x_muse_owner, body.expected_owner)
    try:
        prefs = digest_preview.DigestDraftPreferences(
            cadence=body.cadence,
            topics=body.topics,
            timezone=body.timezone,
            anchor_day=body.anchor_day,
            anchor_date=body.anchor_date,
            competitors=body.competitors,
        )
    except ValueError as err:
        logger.warning("Digest settings invalid (%s)", type(err).__name__)
        raise HTTPException(
            422,
            "Muse couldn't use those digest settings. Choose a timezone such as "
            "America/Los_Angeles and up to 3 public shop links, then try again.",
        ) from err
    return await digest_preview.save_digest_draft(
        account,
        prefs,
        expected_version=body.expected_version,
        expected_owner=body.expected_owner,
    )


@router.post("/preview")
async def preview_personal_digest(
    body: DigestPreviewRequest,
    request: Request,
    response: Response,
    x_muse_owner: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Render a zero-cost personal digest preview using seller memory and saved snapshots."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        raise HTTPException(401, "Sign in to preview your personal digest.")
    verify_workspace_owner(account, x_muse_owner, body.expected_owner)

    overrides: digest_preview.DigestDraftPreferences | None = None
    if any(
        val is not None
        for val in (
            body.cadence,
            body.topics,
            body.timezone,
            body.anchor_day,
            body.anchor_date,
            body.competitors,
        )
    ):
        saved = await digest_preview.load_digest_draft(account)
        merged = dict(saved["draft_preferences"])
        if body.cadence is not None:
            merged["cadence"] = body.cadence
        if body.topics is not None:
            merged["topics"] = body.topics
        if body.timezone is not None:
            merged["timezone"] = body.timezone
        if body.anchor_day is not None:
            merged["anchor_day"] = body.anchor_day
        if body.anchor_date is not None:
            merged["anchor_date"] = body.anchor_date
        if body.competitors is not None:
            merged["competitors"] = body.competitors
        try:
            overrides = digest_preview.DigestDraftPreferences.model_validate(merged)
        except ValueError as err:
            logger.warning("Digest preview settings invalid (%s)", type(err).__name__)
            raise HTTPException(
                422,
                "Muse couldn't use those digest settings. Choose a timezone such as "
                "America/Los_Angeles and up to 3 public shop links, then try again.",
            ) from err

    return await digest_preview.build_personal_digest_preview(account, overrides=overrides)
