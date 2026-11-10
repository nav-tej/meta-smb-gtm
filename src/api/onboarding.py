"""Server-side onboarding completion and run accounting.

Binds onboarding completion to the verified account workspace on the server,
ensuring exactly one run is charged only upon successful persistence, and
idempotently charging zero runs on retry or re-entry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

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

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingBuildRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    business_name: str | None = None
    shop_urls: list[str] = Field(default_factory=list)
    socials: list[dict[str, Any]] = Field(default_factory=list)
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] | None = None
    skipped: list[int] = Field(default_factory=list)
    crawl_summary: dict[str, Any] | None = None
    step: int = 5


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
        onboarding_data = {
            "business_name": body.business_name,
            "shop_urls": body.shop_urls,
            "socials": body.socials,
            "competitors": body.competitors,
            "preferences": body.preferences,
            "skipped": body.skipped,
            "crawl_summary": body.crawl_summary,
            "completed": True,
            "completed_at": now_iso,
            "used_run": False,
        }

        next_doc = dict(doc)
        next_doc["onboarding"] = onboarding_data
        if body.preferences:
            next_doc["preferences"] = body.preferences

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
            raise HTTPException(500, f"Failed to save onboarding workspace: {err}") from err

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
