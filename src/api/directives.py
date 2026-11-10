"""Track I: Research Directive Parsing, Confirmation, and Suggestion Endpoints."""

from __future__ import annotations

import contextlib
import logging
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.models.directive import ResearchDirective, parse_research_directive
from src.services.accounts import (
    load_workspace,
    resolve_account,
    save_workspace,
    verify_workspace_owner,
)
from src.services.directive_limiter import check_directive_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/directives", tags=["directives"])


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class DirectiveResponse(BaseModel):
    directive: ResearchDirective
    summary: str
    cost: str = "0 runs (saved to workspace)"


class SuggestionItem(BaseModel):
    text: str
    focus: str
    reason: str
    cost: str = "0 runs"


class ConfirmDirectiveRequest(BaseModel):
    directive: ResearchDirective


class ConfirmDirectiveResponse(BaseModel):
    status: Literal["confirmed"] = "confirmed"
    directive: ResearchDirective
    summary: str
    cost: str


class ActiveDirectiveResponse(BaseModel):
    directive: ResearchDirective | None = None
    saved_count: int = 0


@router.post("/parse", response_model=DirectiveResponse)
async def parse_directive_endpoint(body: ParseRequest) -> DirectiveResponse:
    """Parse seller query into a typed, syntax-only ResearchDirective.

    NOTE (SYNTAX-ONLY): This endpoint performs text parsing and pattern extraction only;
    it does not execute network fetches, DNS lookups, or crawler execution. Any future
    fetch consumer of directive.competitors_add must validate candidate URLs with
    src.utils.sitemap.validate_safe_url at fetch time.
    """
    directive, summary = parse_research_directive(body.text)
    if not directive:
        raise HTTPException(status_code=400, detail=summary)

    cost = "0 runs (saved to workspace)"
    return DirectiveResponse(directive=directive, summary=summary, cost=cost)


@router.post("/confirm", response_model=ConfirmDirectiveResponse)
async def confirm_directive_endpoint(
    body: ConfirmDirectiveRequest,
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> ConfirmDirectiveResponse:
    """Confirm and persist an active ResearchDirective to the verified account workspace.

    Enforces sliding-window rate limit (max 10 updates per hour) and logs the parsed
    directive structure (never raw free-text prompts) for analytics.
    """
    account = await resolve_account(request, response, require_verified=True)
    if not account:
        raise HTTPException(status_code=401, detail="Create an account and sign in to continue.")
    verify_workspace_owner(account, x_muse_owner, require_binding=True)

    if not check_directive_rate_limit(account.user_id):
        raise HTTPException(
            status_code=429,
            detail=(
                "Research directive rate limit exceeded (maximum 10 per hour). "
                "Please try again later."
            ),
        )

    # Log typed directive properties only (never free-text)
    logger.info(
        "Confirmed research directive for user %s: focus=%s, timeframe=%d, channels=%s",
        account.user_id,
        body.directive.focus,
        body.directive.timeframe_days,
        body.directive.channels,
    )

    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})

    serialized = body.directive.model_dump(mode="json")
    doc["active_directive"] = serialized

    saved = list(doc.get("saved_directives") or [])
    saved = [d for d in saved if d != serialized]
    saved.insert(0, serialized)
    doc["saved_directives"] = saved[:3]

    await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )

    cost = "0 runs (saved to workspace)"
    summary = (
        f"Focus: {body.directive.focus.capitalize()} · "
        f"Window: last {body.directive.timeframe_days} days"
    )
    return ConfirmDirectiveResponse(
        status="confirmed",
        directive=body.directive,
        summary=summary,
        cost=cost,
    )


@router.get("/active", response_model=ActiveDirectiveResponse)
async def get_active_directive(
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> ActiveDirectiveResponse:
    """Retrieve active and saved directive counts for the signed-in account."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        return ActiveDirectiveResponse(directive=None, saved_count=0)

    verify_workspace_owner(account, x_muse_owner)
    ws = await load_workspace(account)
    doc = ws.get("document") or {}
    active_raw = doc.get("active_directive")
    directive = None
    if isinstance(active_raw, dict):
        with contextlib.suppress(Exception):
            directive = ResearchDirective.model_validate(active_raw)
    saved = doc.get("saved_directives") or []
    return ActiveDirectiveResponse(
        directive=directive,
        saved_count=len(saved) if isinstance(saved, list) else 0,
    )


@router.get("/suggestions", response_model=list[SuggestionItem])
async def list_directive_suggestions(
    request: Request,
    response: Response,
) -> list[SuggestionItem]:
    """Return 4 state-derived suggestions that drive usage without model calls.

    For signed-in sellers with custom competitors, suggestions derive from their own
    competitors and preferences. For sample-shop demo sessions, suggestions reference
    the sample fixture (SikhiArt).
    """
    account = await resolve_account(request, response, require_verified=False)
    pricing_text = "Look at why SikhiArt starts at $59.99"
    gifting_text = "Gift ideas for upcoming season"

    if account is not None:
        ws = await load_workspace(account)
        doc = ws.get("document") or {}
        onboarding = doc.get("onboarding") or {}
        comps = onboarding.get("competitors") or []
        shop_name = onboarding.get("business_name") or onboarding.get("shop_name") or ""
        medium = ""
        if isinstance(onboarding.get("preferences"), dict):
            medium = onboarding["preferences"].get("medium") or ""
        if not medium and isinstance(doc.get("preferences"), dict):
            medium = doc["preferences"].get("medium") or ""
        if not medium:
            medium = onboarding.get("medium") or ""

        pricing_text = "Look at why competitor entry prices start higher"
        if comps and isinstance(comps, list) and comps[0]:
            first_name = comps[0].get("name") or comps[0].get("url") or ""
            if first_name and "sikhiart" not in first_name.lower():
                pricing_text = f"Look at why {first_name} starts at higher prices"
        elif shop_name and "sarabjit" not in shop_name.lower():
            pricing_text = "Look at why competitor entry prices start higher"

        if medium:
            gifting_text = f"Gift ideas for {medium} collectors"

    return [
        SuggestionItem(
            text=pricing_text,
            focus="pricing",
            reason="Competitor price gap analysis",
        ),
        SuggestionItem(
            text="Show me easier moves for solo makers",
            focus="difficulty",
            reason="Filter for quick wins under 15 minutes",
        ),
        SuggestionItem(
            text=gifting_text,
            focus="gifting",
            reason="Seasonal holiday gift positioning",
        ),
        SuggestionItem(
            text="What should I post on Instagram this week?",
            focus="posting",
            reason="Weekly social media plan",
        ),
    ]
