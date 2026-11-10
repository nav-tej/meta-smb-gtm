"""Server-side onboarding completion and run accounting.

Binds onboarding completion to the verified account workspace on the server,
ensuring exactly one run is charged only upon successful persistence, and
idempotently charging zero runs on retry or re-entry.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.api.demo import credit_holder, valid_demo_key
from src.config import get_settings
from src.services import credits, usage_meter
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
        snap = await snapshot(account)
        remaining = snap.get("usage", {}).get("remaining")
        return {
            "authenticated": True,
            "completed": bool(onb and onb.get("completed_at")),
            "completed_at": onb.get("completed_at") if onb else None,
            "used_run": bool(onb.get("used_run")) if onb else False,
            "runs_remaining": remaining if remaining is not None else 3,
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
    """Complete onboarding and charge exactly 1 run only on success, once per account."""
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

        # Idempotent check: if already completed, do NOT charge again
        if existing_onb and existing_onb.get("completed_at"):
            snap = await snapshot(account)
            remaining = snap.get("usage", {}).get("remaining")
            return {
                "success": True,
                "charged": False,
                "used_run": bool(existing_onb.get("used_run", False)),
                "runs_remaining": remaining if remaining is not None else 3,
                "completed_at": existing_onb.get("completed_at"),
                "workspace": ws,
                "message": "Onboarding already completed for this account (0 runs charged).",
            }

        # Check remaining runs
        snap = await snapshot(account)
        usage = snap.get("usage") or {}
        remaining = usage.get("remaining")
        if remaining is None:
            holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
            remaining = credits.balance(holder.id)

        charge_run = remaining > 0
        used_run = charge_run
        now_iso = datetime.now(UTC).isoformat()

        onboarding_data = {
            "business_name": body.business_name,
            "shop_urls": body.shop_urls,
            "socials": body.socials,
            "competitors": body.competitors,
            "preferences": body.preferences,
            "skipped": body.skipped,
            "crawl_summary": body.crawl_summary,
            "completed_at": now_iso,
            "used_run": used_run,
        }

        next_doc = dict(doc)
        next_doc["onboarding"] = onboarding_data
        if body.preferences:
            next_doc["preferences"] = body.preferences

        hold = None
        op_id = None
        charged = False

        if charge_run:
            if get_settings().accounts_required:
                ip_src = request.client.host if request.client else "anon"
                op_id = await usage_meter.authorize_operation(
                    account.user_id,
                    hashlib.sha256(ip_src.encode()).hexdigest(),
                    str(uuid4()),
                    account.session_id,
                )
            else:
                holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
                hold = credits.reserve(holder.id, "Onboarding workspace build")

        try:
            saved_ws = await save_workspace(
                account,
                next_doc,
                expected_version=ws.get("version"),
                expected_owner=account.user_id,
            )
            if hold:
                credits.commit(hold)
                charged = True
            elif op_id:
                await usage_meter.finish_operation("completed", operation_id=op_id)
                charged = True
        except Exception as err:
            # REFUND OR CANCEL THE CHARGE: DO NOT MASK THE ERROR!
            if hold:
                credits.refund(hold, "Workspace save failed")
            elif op_id:
                await usage_meter.finish_operation("failed", operation_id=op_id)
            if isinstance(err, HTTPException):
                raise
            raise HTTPException(500, f"Failed to save onboarding workspace: {err}") from err

        updated_snap = await snapshot(account)
        updated_remaining = updated_snap.get("usage", {}).get("remaining")
        if updated_remaining is None:
            holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
            updated_remaining = credits.balance(holder.id)

        return {
            "success": True,
            "charged": charged,
            "used_run": used_run,
            "runs_remaining": updated_remaining,
            "completed_at": now_iso,
            "workspace": saved_ws,
        }

    # 2. DEMO / UNVERIFIED CALLER FLOW
    holder = credit_holder(request, response, presenter=valid_demo_key(x_demo_key))
    info = credits.summary(holder.id)
    # Check if this browser already completed onboarding
    already_done = any(
        h.get("label") == "Onboarding workspace build" and h.get("event") == "spend"
        for h in info.get("history", [])
    )
    if already_done:
        return {
            "success": True,
            "charged": False,
            "used_run": True,
            "runs_remaining": credits.balance(holder.id),
            "completed_at": datetime.now(UTC).isoformat(),
            "message": "Onboarding already completed for this browser (0 runs charged).",
        }

    bal = credits.balance(holder.id)
    now_iso = datetime.now(UTC).isoformat()
    if bal > 0:
        hold = credits.reserve(holder.id, "Onboarding workspace build")
        credits.commit(hold)
        charged = True
        used_run = True
    else:
        charged = False
        used_run = False

    return {
        "success": True,
        "charged": charged,
        "used_run": used_run,
        "runs_remaining": credits.balance(holder.id),
        "completed_at": now_iso,
    }
