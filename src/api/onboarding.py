"""Server-side onboarding completion and run accounting.

Binds onboarding completion to the verified account workspace on the server,
ensuring exactly one run is charged only upon successful persistence, and
idempotently charging zero runs on retry or re-entry.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.api.demo import credit_holder, valid_demo_key
from src.services import credits
from src.services.accounts import (
    load_workspace,
    resolve_account,
    save_workspace,
    snapshot,
    verify_workspace_owner,
)
from src.services.saved_competitors import keep_saved_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_AD_PAGE_ID_RE = re.compile(r"[0-9]{5,20}")


class OnboardingBuildRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    business_name: str | None = None
    shop_urls: list[str] = Field(default_factory=list)
    socials: list[dict[str, Any]] = Field(default_factory=list)
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] | None = None
    memory_entries: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[int] = Field(default_factory=list)
    crawl_summary: dict[str, Any] | None = None
    business_type: Literal["products", "services", "both"] | None = None
    # A seller who already finished setup can come back and change it. Only an explicit edit
    # rewrites a completed setup, so a retried or stale first build stays a no-op.
    edit: bool = False
    step: int = 5


def _merged_preferences(
    body: OnboardingBuildRequest, doc: dict[str, Any], keep_existing: bool = False
) -> dict[str, Any] | None:
    """Setup answers folded into the workspace preferences, or None when setup added none.

    An edit keeps what Muse already saved there (for example seller-memory entries) and
    overwrites only the answers the seller changed.
    """
    if not (body.preferences or body.memory_entries or body.competitors):
        return None
    existing = doc.get("preferences") if isinstance(doc.get("preferences"), dict) else {}
    if keep_existing:
        merged_pref = {**existing, **(body.preferences or {})}
    else:
        merged_pref = dict(body.preferences or existing or {})
    if body.memory_entries:
        merged_pref["memory_entries"] = body.memory_entries
    if body.competitors:
        entries = [
            {
                "name": str(c.get("name") or "")[:140],
                "url": str(c.get("url") or "")[:500],
                "role": (
                    c.get("role")
                    if c.get("role") in {"similar_audience", "price_reference", "inspiration"}
                    else "similar_audience"
                ),
                "rationale": str(c.get("rationale") or c.get("reason") or "")[:280],
                "reason": str(c.get("reason") or c.get("rationale") or "")[:280],
                "selected": c.get("selected", True) is not False,
            }
            | (
                {"ad_library_page_id": str(c["ad_library_page_id"])}
                if _AD_PAGE_ID_RE.fullmatch(str(c.get("ad_library_page_id") or ""))
                else {}
            )
            for c in body.competitors
            if isinstance(c, dict) and c.get("url")
        ]
        # An edit keeps each kept competitor's Ad Library page and saved analysis.
        merged_pref["competitor_entries"] = (
            keep_saved_context(entries, existing.get("competitor_entries"))
            if keep_existing
            else entries
        )
    return merged_pref


def _onboarding_record(
    body: OnboardingBuildRequest, completed_at: str, used_run: bool
) -> dict[str, Any]:
    return {
        "business_name": body.business_name,
        "shop_urls": body.shop_urls,
        "socials": body.socials,
        "competitors": body.competitors,
        "preferences": body.preferences,
        "skipped": body.skipped,
        "crawl_summary": body.crawl_summary,
        "business_type": body.business_type,
        "completed": True,
        "completed_at": completed_at,
        "used_run": used_run,
    }


def _require_json(request: Request) -> None:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "Send onboarding requests as JSON.")


@router.get("/status")
async def onboarding_status(request: Request, response: Response) -> dict[str, Any]:
    """Check current onboarding completion and remaining runs."""
    response.headers["Cache-Control"] = "no-store"
    account = await resolve_account(request, response)
    if account:
        ws = await load_workspace(account)
        onb = ws.get("document", {}).get("onboarding") if ws.get("document") else None
        remaining = 3
        try:
            snap = await snapshot(account)
            rem = snap.get("usage", {}).get("remaining")
            if rem is not None:
                remaining = rem
        except Exception:
            pass
        return {
            "authenticated": True,
            "completed": bool(onb and onb.get("completed_at")),
            "completed_at": onb.get("completed_at") if onb else None,
            "used_run": bool(onb.get("used_run")) if onb else False,
            "runs_remaining": remaining,
            "workspace": ws,
        }
    holder = credit_holder(request, response)
    return {
        "authenticated": False,
        "completed": False,
        "completed_at": None,
        "used_run": False,
        "runs_remaining": credits.balance(holder.id),
        "workspace": None,
    }


@router.post("/build")
@router.post("/complete")
async def complete_onboarding(
    body: OnboardingBuildRequest,
    request: Request,
    response: Response,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Complete onboarding authoritatively: free (0 runs charged), idempotent, once per account."""
    _require_json(request)
    response.headers["Cache-Control"] = "no-store"

    account = await resolve_account(request, response)

    # 1. SIGNED-IN ACCOUNT FLOW
    if account is not None:
        header_owner = request.headers.get("x-muse-owner")
        verify_workspace_owner(account, header_owner=header_owner)

        ws = await load_workspace(account)
        doc = ws.get("document") or {}
        existing_onb = doc.get("onboarding") if isinstance(doc, dict) else None

        remaining = 3
        try:
            snap = await snapshot(account)
            usage = snap.get("usage") or {}
            rem = usage.get("remaining")
            if rem is not None:
                remaining = rem
        except Exception:
            pass

        # Editing a finished setup: save the new answers, keep the original completion record.
        if existing_onb and existing_onb.get("completed_at") and body.edit:
            completed_at = str(existing_onb.get("completed_at"))
            next_doc = dict(doc)
            next_doc["onboarding"] = _onboarding_record(
                body, completed_at, bool(existing_onb.get("used_run"))
            )
            merged = _merged_preferences(body, next_doc, keep_existing=True)
            if merged is not None:
                next_doc["preferences"] = merged
            try:
                saved_ws = await save_workspace(
                    account,
                    next_doc,
                    expected_version=ws.get("version"),
                    expected_owner=account.user_id,
                )
            except Exception as err:
                if isinstance(err, HTTPException):
                    raise
                logger.warning("Setup edit save failed (%s)", type(err).__name__)
                raise HTTPException(
                    500, "Muse couldn't save your setup changes. Try saving again in a minute."
                ) from err
            return {
                "success": True,
                "charged": False,
                "used_run": False,
                "updated": True,
                "runs_remaining": remaining,
                "completed_at": completed_at,
                "workspace": saved_ws,
            }

        # Idempotent check: if already completed, return existing completion record
        if existing_onb and existing_onb.get("completed_at"):
            return {
                "success": True,
                "charged": False,
                "used_run": False,
                "runs_remaining": remaining,
                "completed_at": existing_onb.get("completed_at"),
                "workspace": ws,
                "message": "Onboarding already completed for this account (0 runs charged).",
            }

        now_iso = datetime.now(UTC).isoformat()
        next_doc = dict(doc)
        next_doc["onboarding"] = _onboarding_record(body, now_iso, False)
        merged = _merged_preferences(body, next_doc)
        if merged is not None:
            next_doc["preferences"] = merged

        try:
            saved_ws = await save_workspace(
                account,
                next_doc,
                expected_version=ws.get("version"),
                expected_owner=account.user_id,
            )
        except Exception as err:
            if isinstance(err, HTTPException):
                raise
            logger.warning("Initial setup save failed (%s)", type(err).__name__)
            raise HTTPException(
                500, "Muse couldn't finish saving your setup. Try saving again in a minute."
            ) from err

        return {
            "success": True,
            "charged": False,
            "used_run": False,
            "runs_remaining": remaining,
            "completed_at": now_iso,
            "workspace": saved_ws,
        }

    # 2. DEMO / UNVERIFIED CALLER FLOW (0 runs charged, idempotent)
    holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
    bal = credits.balance(holder.id) if holder else 3
    now_iso = datetime.now(UTC).isoformat()

    return {
        "success": True,
        "charged": False,
        "used_run": False,
        "runs_remaining": bal,
        "completed_at": now_iso,
    }
